import os

with open('pdf_engine/pipeline.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Add import
if 'from pdf_engine.postprocess.normalizer import TextNormalizer' not in content:
    content = content.replace('from pdf_engine.preprocess.context import ContextDetector', 'from pdf_engine.preprocess.context import ContextDetector\nfrom pdf_engine.postprocess.normalizer import TextNormalizer')

# Integrate normalizer
restore_old = '''        # 4. Postprocessor
        self.logger.log("[4/5] Postprocessor: Restoring placeholders...")
        for s in state.segments:
            if s.needs_translation and hasattr(s, 'placeholders'):
                pm = PlaceholderManager.from_dict(s.placeholders)
                try:
                    s.translated = pm.restore(s.translated)'''

restore_new = '''        # 4. Postprocessor
        self.logger.log("[4/5] Postprocessor: Normalizing and restoring placeholders...")
        for s in state.segments:
            if s.needs_translation and hasattr(s, 'placeholders'):
                pm = PlaceholderManager.from_dict(s.placeholders)
                try:
                    # Normalize text BEFORE restoration to avoid mutating protected content
                    s.translated = TextNormalizer.normalize(s.translated)
                    
                    s.translated = pm.restore(s.translated)'''

content = content.replace(restore_old, restore_new)

with open('pdf_engine/pipeline.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('Patched pipeline for normalizer')
