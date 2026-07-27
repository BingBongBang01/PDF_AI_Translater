import os

with open('translate_pdf.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Add argument
arg_old = 'ap.add_argument("--glossary", default=None, help="용어집 파일 (.json 또는 .csv/.txt)")'
arg_new = '''ap.add_argument("--glossary", default=None, help="용어집 파일 (.json, .yaml, .csv)")
    ap.add_argument("--glossary-profile", default="default", help="용어집 프로필 (예: academic, ui)")'''
content = content.replace(arg_old, arg_new)

# Replace load_glossary import and usage
if 'from pdf_engine.glossary.parser import GlossaryParser' not in content:
    content = content.replace('from pdf_engine.pipeline import TranslationPipeline', 'from pdf_engine.glossary.parser import GlossaryParser\nfrom pdf_engine.pipeline import TranslationPipeline')

usage_old = 'glossary_text = load_glossary(args.glossary)'
usage_new = '''glossary_map = GlossaryParser.load(args.glossary, args.glossary_profile)
        glossary_text = ""
        for k, v in glossary_map.items():
            glossary_text += f"{k} => {v}\\n"
        '''
content = content.replace(usage_old, usage_new)

# Also update the pipeline initialization
pipe_old = '''pipeline = TranslationPipeline(
            args=args, system_prompt=system_prompt, template=template,
            glossary_text=glossary_text, pool=pool, system_prompt_local=system_prompt_local
        )'''

pipe_new = '''pipeline = TranslationPipeline(
            args=args, system_prompt=system_prompt, template=template,
            glossary_text=glossary_text, pool=pool, system_prompt_local=system_prompt_local,
            glossary_map=glossary_map
        )'''
content = content.replace(pipe_old, pipe_new)

with open('translate_pdf.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('Patched translate_pdf.py for glossary')
