import string
from typing import Dict, Any, List

class PromptBuilder:
    """Builds prompts dynamically using template substitution."""
    
    def __init__(self, template_str: str):
        self.template = string.Template(template_str)
        self.context: Dict[str, str] = {
            "previous_chunk": "",
            "next_chunk": "",
            "glossary": "",
            "translation_memory": "",
            "custom_rules": ""
        }
        
    def add_context(self, key: str, value: str) -> None:
        self.context[key] = value
        
    def build(self, source_text: str, source_lang: str, target_lang: str) -> str:
        # Prevents string concatenation errors by strictly using safe_substitute
        mapping = {
            "source_text": source_text,
            "source_lang": source_lang,
            "target_lang": target_lang,
            **self.context
        }
        return self.template.safe_substitute(mapping)
