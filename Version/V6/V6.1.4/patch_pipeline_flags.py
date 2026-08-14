import os
import re

with open('pdf_engine/pipeline.py', 'r', encoding='utf-8') as f:
    content = f.read()

if 'from pdf_engine.config.settings import FeatureFlags' not in content:
    content = content.replace('import pymupdf', 'import pymupdf\nimport time\nfrom pdf_engine.config.settings import FeatureFlags')

pre_old = '''        # 1. Preprocessor
        self.logger.log("[1/5] Preprocessor: Extracting segments...")
        page_filter = getattr(self.args, 'page_filter', None)
        translate_all = getattr(self.args, 'translate_all', False)
        tessdata_dir = getattr(self.args, 'tessdata_dir', None)
        ocr_lang = resolve_ocr_lang(self.args.source_lang, getattr(self.args, 'ocr_lang', None))
        
        state.segments = extract_segments(state.doc, page_filter, translate_all, tessdata_dir=tessdata_dir, ocr_lang=ocr_lang)
        if not getattr(self.args, 'no_merge', False):
            state.segments = merge_adjacent_segments(state.segments)'''

pre_new = '''        # Load feature flags
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
        self.logger.log(f"[METRIC] Preprocessing took {time.time()-t0:.2f}s")'''

content = content.replace(pre_old, pre_new)

ctx_old = '''        # 1.5 Context Detection & Strategy Routing
        context_profile = getattr(self.args, "glossary_profile", "auto")
        if context_profile == "auto" and self.pool:
            self.logger.log("[1.5/5] Context Detection: Analyzing document tone...")
            detected_context = ContextDetector.detect(self.pool, state.segments)
            
            # Mutate strategy
            self.system_prompt += f"\\n\\n[STRATEGY]\\nThe context of this document is detected as '{detected_context}'. Please adopt an appropriate tone and vocabulary."
            self.logger.log(f"[INFO] Routing translation strategy to profile: {detected_context}")
            
            if getattr(self.args, "glossary", None):
                self.glossary_map = GlossaryParser.load(self.args.glossary, detected_context)'''

ctx_new = '''        # 1.5 Context Detection & Strategy Routing
        context_profile = getattr(self.args, "glossary_profile", "auto")
        t1 = time.time()
        if FeatureFlags.enable_context_detection and context_profile == "auto" and self.pool:
            self.logger.log("[1.5/5] Context Detection: Analyzing document tone...")
            detected_context = ContextDetector.detect(self.pool, state.segments)
            
            # Mutate strategy
            self.system_prompt += f"\\n\\n[STRATEGY]\\nThe context of this document is detected as '{detected_context}'. Please adopt an appropriate tone and vocabulary."
            self.logger.log(f"[INFO] Routing translation strategy to profile: {detected_context}")
            
            if FeatureFlags.enable_glossary and getattr(self.args, "glossary", None):
                self.glossary_map = GlossaryParser.load(self.args.glossary, detected_context)
            self.logger.log(f"[METRIC] Context Detection took {time.time()-t1:.2f}s")'''

content = content.replace(ctx_old, ctx_new)

ph_old = '''        # 2. Placeholder Manager
        self.logger.log("[2/5] Placeholder Manager: Protecting tokens...")
        for s in state.segments:
            if s.needs_translation:
                pm = PlaceholderManager(glossary_map=self.glossary_map)
                s.text = pm.protect(s.text)
                s.placeholders = pm.to_dict()'''

ph_new = '''        # 2. Placeholder Manager
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
            self.logger.log(f"[METRIC] Placeholder Engine took {time.time()-t2:.2f}s")'''

content = content.replace(ph_old, ph_new)

trans_old = '''        # 3. Translation Engine
        self.logger.log("[3/5] Translation Engine: Processing batches...")
        translate_all_batches(
            self.pool, self.args, self.system_prompt, self.template, state.segments,
            self.glossary_text, system_prompt_local=self.system_prompt_local, pbar_callback=self.pbar_callback
        )'''

trans_new = '''        # 3. Translation Engine
        t3 = time.time()
        self.logger.log("[3/5] Translation Engine: Processing batches...")
        g_text = self.glossary_text if FeatureFlags.enable_glossary else ""
        translate_all_batches(
            self.pool, self.args, self.system_prompt, self.template, state.segments,
            g_text, system_prompt_local=self.system_prompt_local, pbar_callback=self.pbar_callback
        )
        self.logger.log(f"[METRIC] Translation Engine took {time.time()-t3:.2f}s")'''

content = content.replace(trans_old, trans_new)

post_old = '''        # 4. Postprocessor and Validator
        self.logger.log("[4/5] Postprocessor: Validating and Restoring placeholders...")
        for s in state.segments:
            if s.needs_translation and s.translated:
                try:
                    if getattr(s, "placeholders", None):
                        pm = PlaceholderManager.from_dict(s.placeholders)
                        
                        # Validate before restore (checks missing/duplicate tokens)
                        ValidationEngine.validate_pre_restore(s.translated, s.text)
                        
                        # Normalize and restore
                        s.translated = TextNormalizer.normalize(s.translated)
                        s.translated = pm.restore(s.translated)
                        
                    # Validate after restore (syntax and format checks)
                    ValidationEngine.validate_post_restore(s.translated)
                    
                except ValidationError as e:
                    self.logger.log(f"[FATAL] Validation failed on segment {s.seg_id}: {e}", level="ERROR")
                    raise RuntimeError(f"Translation validation failed: {e}")
                except PlaceholderRestorationError as e:
                    self.logger.log(f"[FATAL] Placeholder restoration failed for segment {s.seg_id}: {e}", level="ERROR")
                    raise RuntimeError(f"Placeholder corruption: {e}")'''

post_new = '''        # 4. Postprocessor and Validator
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
        self.logger.log(f"[METRIC] Postprocessor took {time.time()-t4:.2f}s")'''

content = content.replace(post_old, post_new)

with open('pdf_engine/pipeline.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('Patched pipeline for flags and timing')
