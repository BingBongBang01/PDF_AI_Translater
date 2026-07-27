import pymupdf
import time
from pdf_engine.config.settings import FeatureFlags
from typing import Any, Callable, List
from pathlib import Path
from pdf_engine.logger import get_logger
from pdf_engine.preprocess.context import ContextDetector
from pdf_engine.validator.engine import ValidationEngine, ValidationError
from pdf_engine.postprocess.normalizer import TextNormalizer
from pdf_engine.postprocess.normalizer import TextNormalizer
from pdf_engine.glossary.parser import GlossaryParser
from pdf_engine.preprocess.extractor import extract_segments, merge_adjacent_segments, resolve_ocr_lang
from pdf_engine.placeholder.manager import PlaceholderManager, PlaceholderRestorationError
from pdf_engine.translator.scheduler import translate_all_batches
from pdf_engine.postprocess.renderer import rebuild_pdf

class PipelineState:
    def __init__(self, doc: pymupdf.Document, args: Any):
        self.doc = doc
        self.args = args
        self.segments = []
        self.tmp_path: Path = None
        self.current_target_pages = set()

class TranslationPipeline:
    def __init__(self, args: Any, system_prompt: str, template: str, glossary_text: str, pool: list, system_prompt_local: str = None, pbar_callback: Callable = None, glossary_map: dict = None):
        self.args = args
        self.system_prompt = system_prompt
        self.template = template
        self.glossary_text = glossary_text
        self.glossary_map = glossary_map or {}
        self.pool = pool
        self.system_prompt_local = system_prompt_local
        self.pbar_callback = pbar_callback
        self.logger = get_logger()

    def run_translation_phase(self, state: PipelineState) -> PipelineState:
        self.logger.log("Starting Translation Phase")
        
        # Load feature flags
        FeatureFlags.load_from_args(self.args)
        
        # 1. Preprocessor
        t0 = time.time()
        self.logger.log("[1/5] Preprocessor: Extracting segments...")
        page_filter = getattr(self.args, 'page_filter', None)
        translate_all = getattr(self.args, 'translate_all', False)
        tessdata_dir = getattr(self.args, 'tessdata_dir', None)
        ocr_lang = resolve_ocr_lang(self.args.source_lang, getattr(self.args, 'ocr_lang', None))
        
        state.segments = extract_segments(state.doc, page_filter, translate_all, tessdata_dir=tessdata_dir, ocr_lang=ocr_lang)
        if not getattr(self.args, 'no_merge', False):
            state.segments = merge_adjacent_segments(state.segments)
        self.logger.log(f"[METRIC] Preprocessing took {time.time()-t0:.2f}s")

        # 1.5 Context Detection & Strategy Routing
        context_profile = getattr(self.args, "glossary_profile", "auto")
        t1 = time.time()
        if FeatureFlags.enable_context_detection and context_profile == "auto" and self.pool:
            self.logger.log("[1.5/5] Context Detection: Analyzing document tone...")
            detected_context = ContextDetector.detect(self.pool, state.segments)
            
            # Mutate strategy
            self.system_prompt += f"\n\n[STRATEGY]\nThe context of this document is detected as '{detected_context}'. Please adopt an appropriate tone and vocabulary."
            self.logger.log(f"[INFO] Routing translation strategy to profile: {detected_context}")
            
            if FeatureFlags.enable_glossary and getattr(self.args, "glossary", None):
                self.glossary_map = GlossaryParser.load(self.args.glossary, detected_context)
            self.logger.log(f"[METRIC] Context Detection took {time.time()-t1:.2f}s")
                
        # 2. Placeholder Manager
        t2 = time.time()
        if FeatureFlags.enable_placeholder:
            self.logger.log("[2/5] Placeholder Manager: Protecting tokens...")
            for s in state.segments:
                if s.needs_translation:
                    # Pass glossary map only if glossary is enabled
                    g_map = self.glossary_map if FeatureFlags.enable_glossary else {}
                    pm = PlaceholderManager(glossary_map=g_map)
                    s.text = pm.protect(s.text)
                    s.placeholders = pm.to_dict()
            self.logger.log(f"[METRIC] Placeholder Engine took {time.time()-t2:.2f}s")

        # 3. Translation Engine
        t3 = time.time()
        self.logger.log("[3/5] Translation Engine: Processing batches...")
        g_text = self.glossary_text if FeatureFlags.enable_glossary else ""
        translate_all_batches(
            self.pool, self.args, self.system_prompt, self.template, state.segments,
            g_text, system_prompt_local=self.system_prompt_local, pbar_callback=self.pbar_callback
        )
        self.logger.log(f"[METRIC] Translation Engine took {time.time()-t3:.2f}s")
        if getattr(self.args, 'stop_event', None) and getattr(self.args.stop_event, 'is_set', lambda: False)():
            self.logger.log("[WARNING] Translation aborted by user.")

        # 4. Postprocessor and Validator
        t4 = time.time()
        self.logger.log("[4/5] Postprocessor: Validating and Restoring placeholders...")
        for s in state.segments:
            if s.needs_translation and s.translated:
                try:
                    if getattr(s, "placeholders", None) and FeatureFlags.enable_placeholder:
                        pm = PlaceholderManager.from_dict(s.placeholders)
                        
                        if FeatureFlags.enable_validation:
                            ValidationEngine.validate_pre_restore(s.translated, s.text)
                        
                        if FeatureFlags.enable_style_fix:
                            s.translated = TextNormalizer.normalize(s.translated)
                            
                        s.translated = pm.restore(s.translated)
                        
                    if FeatureFlags.enable_validation:
                        ValidationEngine.validate_post_restore(s.translated)
                    
                except ValidationError as e:
                    self.logger.log(f"[FATAL] Validation failed on segment {s.seg_id}: {e}", level="ERROR")
                    raise RuntimeError(f"Translation validation failed: {e}")
                except PlaceholderRestorationError as e:
                    self.logger.log(f"[FATAL] Placeholder restoration failed for segment {s.seg_id}: {e}", level="ERROR")
                    raise RuntimeError(f"Placeholder corruption: {e}")
        self.logger.log(f"[METRIC] Postprocessor took {time.time()-t4:.2f}s")

        # 5. Validation and Output (Rebuild PDF)
        return state

    def run_output_phase(self, state: PipelineState) -> PipelineState:
        if state.tmp_path:
            self.logger.log("[5/5] Validation & Output: Rebuilding PDF...")
            work_doc = None
            try:
                work_doc = pymupdf.open(state.tmp_path)
                if work_doc.needs_pass:
                    raise RuntimeError("Temporary PDF is encrypted.")
                
                rebuild_pdf(work_doc, state.segments, getattr(self.args, 'font_scale', 1.0))
                
                if work_doc.can_save_incrementally():
                    work_doc.saveIncr()
                else:
                    patch_path = state.tmp_path.with_name(state.tmp_path.stem + ".patch.pdf")
                    patched_pages = sorted(state.current_target_pages)
                    patch_doc = pymupdf.open()
                    for page_no in patched_pages:
                        patch_doc.insert_pdf(work_doc, from_page=page_no - 1, to_page=page_no - 1)
                    patch_doc.save(patch_path)
                    patch_doc.close()
                    work_doc.close()
                    work_doc = None
                    
                    final_doc = pymupdf.open(state.tmp_path)
                    patch_doc_in = pymupdf.open(patch_path)
                    for idx, page_no in enumerate(patched_pages):
                        final_doc.delete_page(page_no - 1)
                        final_doc.insert_pdf(patch_doc_in, from_page=idx, to_page=idx, start_at=page_no - 1)
                    final_doc.saveIncr()
                    final_doc.close()
                    patch_doc_in.close()
                    patch_path.unlink()
            finally:
                if work_doc:
                    work_doc.close()
        
        return state
