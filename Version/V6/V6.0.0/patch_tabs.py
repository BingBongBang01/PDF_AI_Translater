import os, re
import pprint

files = [
    'ui/windows/pages/about_page.py',
    'ui/windows/pages/export_page.py',
    'ui/windows/pages/history_page.py',
    'ui/windows/pages/ocr_page.py',
    'ui/windows/pages/pdf_page.py',
    'ui/windows/pages/translate_page.py',
    'ui/widgets/translation_settings_panel.py',
    'ui/widgets/translation_stats_panel.py',
    'ui/widgets/translation_memory_table.py',
    'ui/widgets/translation_queue_table.py'
]

patterns = [
    r'(MaterialLabel\()(\"[^\"]+\")(\))',
    r'(MaterialButton\()(\"[^\"]+\")(\))',
    r'(MaterialCheckBox\()(\"[^\"]+\")(\))',
    r'(MaterialGroupBox\()(\"[^\"]+\")(\))',
    r'(InfoCard\()(\"[^\"]+\")(\,)',
]

strings_found = set()

for f in files:
    try:
        if not os.path.exists(f):
            continue
        content = open(f, 'r', encoding='utf-8').read()
        
        def replacer(match):
            s = match.group(2)
            if s == '\"\"':
                return match.group(0)
            strings_found.add(s.strip('\"'))
            return f'{match.group(1)}tr({s}){match.group(3)}'

        for p in patterns:
            content = re.sub(p, replacer, content)
            
        def replacer_addrow(match):
            s = match.group(1)
            strings_found.add(s.strip('\"'))
            return f'addRow(tr({s}),'
        
        content = re.sub(r'addRow\((\"[^\"]+\")\,', replacer_addrow, content)
        
        open(f, 'w', encoding='utf-8').write(content)
    except Exception as e:
        print(f, e)

print('Strings Found:')
pprint.pprint(sorted(list(strings_found)))
