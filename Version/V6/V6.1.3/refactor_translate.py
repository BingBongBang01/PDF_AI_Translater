import os
import re

with open('translate_pdf.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Add imports
if 'from pdf_engine.pipeline import TranslationPipeline, PipelineState' not in content:
    content = content.replace('from pdf_engine.preprocess.extractor import', 'from pdf_engine.pipeline import TranslationPipeline, PipelineState\nfrom pdf_engine.preprocess.extractor import')

# We need to replace the huge chunk from extract_segments down to the end of rebuild_pdf.
# In translate_pdf.py around line 261:
# segments = extract_segments(doc, page_filter, args.translate_all, ...)
# ...
# patch_path.unlink()

# Since writing robust regex for that is hard, I will use Python logic to find lines and replace them.
lines = content.split('\n')
start_idx = -1
end_idx = -1

for i, line in enumerate(lines):
    if 'segments = extract_segments(doc' in line:
        start_idx = i
        break

for i in range(start_idx, len(lines)):
    if 'patch_path.unlink()' in line:
        # Actually it's inside `try...finally: if work_doc: work_doc.close()`
        pass

# It's better to just do this manually with replace_file_content if I know the exact lines, but wait...
