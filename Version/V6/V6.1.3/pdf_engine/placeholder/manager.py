import re
from typing import Dict, Any

class PlaceholderRestorationError(Exception):
    """Raised when placeholders fail to restore properly."""
    pass

class PlaceholderManager:
    def __init__(self, mapping: Dict[str, str] = None, counter: int = 0, glossary_map: Dict[str, str] = None, gl_counter: int = 0):
        self.glossary_map = glossary_map or {}
        self.gl_counter = gl_counter
        self.mapping = mapping or {}
        self.counter = counter
        self.gl_mapping = {}

    def protect(self, text: str) -> str:
        protected_text = text
        
        # 1. Protect Glossary terms first (so they can be nested inside other formats)
        if getattr(self, 'glossary_map', None):
            sorted_terms = sorted(self.glossary_map.keys(), key=len, reverse=True)
            for term in sorted_terms:
                idx = 0
                while True:
                    idx = protected_text.find(term, idx)
                    if idx == -1:
                        break
                    
                    placeholder = f"⟦GL{self.gl_counter}⟧"
                    target_translation = self.glossary_map[term]
                    self.gl_mapping[placeholder] = target_translation
                    self.gl_counter += 1
                    
                    protected_text = protected_text[:idx] + placeholder + protected_text[idx + len(term):]
                    idx += len(placeholder)

        # Order matters! Largest/most complex first for nested support.
        patterns = [
            # Code blocks
            r'```[\s\S]*?```',
            r'`[^`\n]+`',
            # Markdown links (e.g. [text](url))
            r'\[[^\]]+\]\([^)]+\)',
            # HTML tags
            r'<[^>]+>',
            # Emails
            r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+',
            # URLs
            r'https?://[^\s<>\"\'\]\)]+',
            # Mentions
            r'@[a-zA-Z0-9_]+',
            # Hashtags
            r'#[a-zA-Z0-9_]+',
            # Markdown bold/italic
            r'\*\*[^\n]+\*\*',
            r'__[^\n]+__',
            r'\*[^\n]+\*',
            r'_[^\n]+_'
        ]
        
        for pattern in patterns:
            while True:
                match = re.search(pattern, protected_text)
                if not match:
                    break
                raw_token = match.group(0)
                
                # Check if it's already a placeholder being rematched (avoids infinite loop)
                if raw_token.startswith("⟦PH") and raw_token.endswith("⟧"):
                    break
                    
                placeholder = f"⟦PH{self.counter}⟧"
                self.mapping[placeholder] = raw_token
                self.counter += 1
                
                # Replace only the first occurrence to allow nested mapping
                protected_text = protected_text[:match.start()] + placeholder + protected_text[match.end():]
                
        return protected_text
        
    def restore(self, text: str) -> str:
        import re
        restored = text
        
        sorted_placeholders = sorted(
            self.mapping.items(), 
            key=lambda item: int(item[0].replace("⟦PH", "").replace("⟧", "")), 
            reverse=True
        )
        
        for ph, raw in sorted_placeholders:
            if ph not in restored:
                raise PlaceholderRestorationError(f"Missing placeholder {ph} in translation.")
            restored = restored.replace(ph, raw)
            
        leftover = re.search(r'⟦PH\d+⟧', restored)
        if leftover:
            raise PlaceholderRestorationError(f"Unresolved placeholder found: {leftover.group(0)}")
            
        # Restore glossary placeholders
        for gl_ph, target_text in getattr(self, 'gl_mapping', {}).items():
            if gl_ph not in restored:
                raise PlaceholderRestorationError(f"Missing glossary placeholder {gl_ph} in translation.")
            restored = restored.replace(gl_ph, target_text)
            
        leftover_gl = re.search(r'⟦GL\d+⟧', restored)
        if leftover_gl:
            raise PlaceholderRestorationError(f"Unresolved glossary placeholder found: {leftover_gl.group(0)}")
            
        return restored

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mapping": self.mapping,
            "counter": self.counter,
            "gl_mapping": getattr(self, 'gl_mapping', {}),
            "gl_counter": getattr(self, 'gl_counter', 0)
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PlaceholderManager':
        inst = cls(mapping=data.get("mapping", {}), counter=data.get("counter", 0))
        inst.gl_mapping = data.get("gl_mapping", {})
        inst.gl_counter = data.get("gl_counter", 0)
        return inst
