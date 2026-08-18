import pymupdf
import re
import time
from pdf_engine.config.settings import FeatureFlags
from typing import Any, Callable, List
from pathlib import Path
from pdf_engine.logger import get_logger
from pdf_engine.preprocess.context import ContextDetector
from pdf_engine.validator.engine import ValidationEngine, ValidationError
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
        self.aborted = False   # True면 번역 수단 소진/사용자 중단으로 일부만 번역됨

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

    def _degrade_segment(self, s, reason: str) -> None:
        """
        세그먼트 하나를 '번역 실패(원문 유지)'로 강등한다. 문서 전체를 버리지 않기 위한
        안전장치이며, 원문 유지로 남은 페이지는 출력 파일명의 미번역 구간으로 기록되어
        나중에 그 부분만 이어서 번역할 수 있다.
        """
        fallback = getattr(s, "raw_text", None)
        if fallback is None:
            fallback = s.text
            if getattr(s, "placeholders", None):
                try:  # 토큰이 남은 원문이라면 최대한 되돌려서 ⟦PH0⟧ 노출을 막는다
                    fallback = PlaceholderManager.from_dict(s.placeholders).restore(s.text)
                except Exception:
                    fallback = re.sub(r"⟦(?:PH|GL)\d+⟧", "", s.text)
        s.translated = fallback
        s.translation_failed = True
        self.logger.log(f"[경고] 세그먼트 {s.seg_id} {reason[:160]} -> 원문 유지", level="WARNING")

    def run_translation_phase(self, state: PipelineState) -> PipelineState:
        self.logger.log("Starting Translation Phase")
        
        # Load feature flags
        FeatureFlags.load_from_args(self.args)
        
        # 1. Preprocessor
        # 호출측(main)이 이미 추출해서 state.segments에 넣어줬으면 다시 추출하지 않는다.
        # (예전엔 무조건 다시 추출해서 추출/OCR을 두 번 돌렸다 - 스캔본에서는 이 중복이
        #  전체 처리 시간을 그대로 두 배로 만들었다.)
        t0 = time.time()
        if state.segments:
            self.logger.log(f"[1/5] Preprocessor: 이미 추출된 세그먼트 {len(state.segments)}개 재사용")
        else:
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
                    s.raw_text = s.text          # 복원 실패 시 되돌릴 진짜 원문
                    s.text = pm.protect(s.text)
                    s.placeholders = pm.to_dict()
            self.logger.log(f"[METRIC] Placeholder Engine took {time.time()-t2:.2f}s")

        # 3. Translation Engine
        t3 = time.time()
        self.logger.log("[3/5] Translation Engine: Processing batches...")
        g_text = self.glossary_text if FeatureFlags.enable_glossary else ""
        state.aborted = translate_all_batches(
            self.pool, self.args, self.system_prompt, self.template, state.segments,
            g_text, system_prompt_local=self.system_prompt_local, pbar_callback=self.pbar_callback
        )
        self.logger.log(f"[METRIC] Translation Engine took {time.time()-t3:.2f}s")
        if getattr(self.args, 'stop_event', None) and getattr(self.args.stop_event, 'is_set', lambda: False)():
            self.logger.log("[WARNING] Translation aborted by user.")

        # 4. Postprocessor and Validator
        #
        # 중요: 여기서 실패하는 것은 "세그먼트 하나의 번역문 품질"이지 문서 전체가 아니다.
        # 예전에는 검증/복원 실패 하나가 RuntimeError로 위까지 올라가 main()을 통째로
        # 죽였고, 그러면 [4] 재구성 단계에 도달하지 못해 이미 몇 시간 걸려 번역해 둔
        # 결과가 PDF로 저장되지 않고 전부 사라졌다(실제 확인된 문제: 로컬 NPU로 거의
        # 끝까지 번역한 뒤 마지막 단계에서 오류가 나며 진행분이 통째로 날아감).
        # 소형 로컬 모델은 ⟦PH0⟧ 같은 보호 토큰을 빠뜨리는 일이 흔해서 이 실패는
        # '예외적 상황'이 아니라 '자주 있는 일'이다. 따라서 해당 세그먼트만 원문 유지로
        # 되돌리고(translation_failed=True) 나머지는 정상 저장한다 - 그러면 출력 파일명의
        # 미번역 구간으로 기록되어 나중에 그 부분만 이어서 번역할 수 있다.
        t4 = time.time()
        self.logger.log("[4/5] Postprocessor: Validating and Restoring placeholders...")
        degraded = 0
        for s in state.segments:
            if not (s.needs_translation and s.translated):
                continue
            translated_before = s.translated
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

            except Exception as e:
                kind = ("검증" if isinstance(e, ValidationError)
                        else "플레이스홀더 복원" if isinstance(e, PlaceholderRestorationError)
                        else "후처리")
                s.translated = translated_before
                self._degrade_segment(s, f"{kind} 실패: {e}")
                degraded += 1

        # 보호 토큰이 남은 s.text를 원문으로 되돌린다(내보내기/재시도 경로에서 ⟦PH0⟧가
        # 그대로 새어 나가지 않도록).
        for s in state.segments:
            if getattr(s, "raw_text", None) is not None:
                s.text = s.raw_text

        if degraded:
            self.logger.log(f"[경고] {degraded}개 세그먼트가 후처리 검증/복원에 실패해 "
                            f"원문 유지로 처리됨 (나머지는 정상 저장됨).")
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
