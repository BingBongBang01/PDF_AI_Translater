import os
import re

with open('pdf_engine/pipeline.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Add imports for ContextDetector
if 'from pdf_engine.preprocess.context import ContextDetector' not in content:
    content = content.replace('from pdf_engine.preprocess.extractor import', 'from pdf_engine.preprocess.context import ContextDetector\nfrom pdf_engine.glossary.parser import GlossaryParser\nfrom pdf_engine.preprocess.extractor import')

# Insert context detection right after preprocessing
pre_old = '''        # 2. Placeholder Manager
        self.logger.log("[2/5] Placeholder Manager: Protecting tokens...")'''

pre_new = '''        # 1.5 Context Detection & Strategy Routing
        context_profile = getattr(self.args, "glossary_profile", "auto")
        if context_profile == "auto" and self.pool:
            self.logger.log("[1.5/5] Context Detection: Analyzing document tone...")
            detected_context = ContextDetector.detect(self.pool, state.segments)
            
            # Mutate strategy
            self.system_prompt += f"\\n\\n[STRATEGY]\\nThe context of this document is detected as '{detected_context}'. Please adopt an appropriate tone and vocabulary."
            self.logger.log(f"[INFO] Routing translation strategy to profile: {detected_context}")
            
            if getattr(self.args, "glossary", None):
                self.glossary_map = GlossaryParser.load(self.args.glossary, detected_context)
                
        # 2. Placeholder Manager
        self.logger.log("[2/5] Placeholder Manager: Protecting tokens...")'''

content = content.replace(pre_old, pre_new)

with open('pdf_engine/pipeline.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('Patched pipeline for context detection')
