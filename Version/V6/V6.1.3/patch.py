import os, re

for filepath in ['translate_pdf.py', 'gui.py']:
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # Update import
    if 'from pdf_engine.placeholder.manager import PlaceholderManager, PlaceholderRestorationError' not in content:
        content = content.replace('from pdf_engine.preprocess.protector import TextProtector', 'from pdf_engine.placeholder.manager import PlaceholderManager, PlaceholderRestorationError')
    
    content = content.replace('s.protector = TextProtector()', 'pm = PlaceholderManager()')
    content = content.replace('s.text = s.protector.protect(s.text)', 's.text = pm.protect(s.text)\n                    s.placeholders = pm.to_dict()')
    
    restore_new = '''if s.needs_translation and s.translated and getattr(s, "placeholders", None):
                    try:
                        pm = PlaceholderManager.from_dict(s.placeholders)
                        s.translated = pm.restore(s.translated)
                    except PlaceholderRestorationError as e:
                        from pdf_engine.logger import get_logger
                        get_logger().log(f"[WARNING] Placeholder restoration failed for segment {s.seg_id}: {e}", level="WARN")
                        s.translation_failed = True
                        s.translated = s.text'''
    
    content = re.sub(r'if s\.needs_translation and s\.translated and s\.protector:.*?s\.translated = s\.protector\.restore\(s\.translated\)', restore_new, content, flags=re.DOTALL)

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
print('Updated translate_pdf.py and gui.py')
