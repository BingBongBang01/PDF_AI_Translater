import os

with open('pdf_engine/pipeline.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Add import
if 'from pdf_engine.validator.engine import ValidationEngine, ValidationError' not in content:
    content = content.replace('from pdf_engine.postprocess.normalizer import TextNormalizer', 'from pdf_engine.postprocess.normalizer import TextNormalizer\nfrom pdf_engine.validator.engine import ValidationEngine, ValidationError')

# Modify postprocessor
restore_old = '''        # 4. Postprocessor (Restore placeholders)
        self.logger.log("[4/5] Postprocessor: Restoring placeholders...")
        for s in state.segments:
            if s.needs_translation and s.translated and getattr(s, "placeholders", None):
                try:
                    pm = PlaceholderManager.from_dict(s.placeholders)
                    s.translated = pm.restore(s.translated)
                except PlaceholderRestorationError as e:
                    self.logger.log(f"[WARNING] Placeholder restoration failed for segment {s.seg_id}: {e}", level="WARN")
                    s.translation_failed = True
                    s.translated = s.text'''

restore_new = '''        # 4. Postprocessor and Validator
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

content = content.replace(restore_old, restore_new)

with open('pdf_engine/pipeline.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('Patched pipeline for validator')
