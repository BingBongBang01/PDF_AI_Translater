import os

with open('pdf_engine/pipeline.py', 'r', encoding='utf-8') as f:
    content = f.read()

# I also need to parse the glossary file!
# Wait, `pipeline.py` currently receives `self.glossary_text` (a raw string from load_glossary in translate_pdf.py).
# We should change `TranslationPipeline` to receive `glossary_map: dict = None`.

content = content.replace('def __init__(self, args: Any, system_prompt: str, template: str, glossary_text: str, pool: list, system_prompt_local: str = None, pbar_callback: Callable = None):', 'def __init__(self, args: Any, system_prompt: str, template: str, glossary_text: str, pool: list, system_prompt_local: str = None, pbar_callback: Callable = None, glossary_map: dict = None):')

content = content.replace('self.glossary_text = glossary_text', 'self.glossary_text = glossary_text\n        self.glossary_map = glossary_map or {}')

protect_old = '''        # 2. Placeholder Manager
        self.logger.log("[2/5] Placeholder Manager: Protecting tokens...")
        for s in state.segments:
            if s.needs_translation:
                pm = PlaceholderManager()'''

protect_new = '''        # 2. Placeholder Manager
        self.logger.log("[2/5] Placeholder Manager: Protecting tokens...")
        for s in state.segments:
            if s.needs_translation:
                pm = PlaceholderManager(glossary_map=self.glossary_map)'''

content = content.replace(protect_old, protect_new)

with open('pdf_engine/pipeline.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('Patched pipeline')
