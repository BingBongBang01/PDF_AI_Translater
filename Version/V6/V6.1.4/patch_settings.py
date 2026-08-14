import os

with open('pdf_engine/config/settings.py', 'r', encoding='utf-8') as f:
    content = f.read()

feature_flags = '''
class FeatureFlags:
    """Global feature toggles for the translation pipeline."""
    enable_glossary = True
    enable_validation = True
    enable_placeholder = True
    enable_context_detection = True
    enable_style_fix = True

    @classmethod
    def load_from_args(cls, args):
        cls.enable_glossary = not getattr(args, "disable_glossary", False)
        cls.enable_validation = not getattr(args, "disable_validation", False)
        cls.enable_placeholder = not getattr(args, "disable_placeholder", False)
        cls.enable_context_detection = not getattr(args, "disable_context_detection", False)
        cls.enable_style_fix = not getattr(args, "disable_style_fix", False)
'''

if 'class FeatureFlags:' not in content:
    content += feature_flags

with open('pdf_engine/config/settings.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('Patched settings.py for FeatureFlags')
