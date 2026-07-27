import os

with open('pdf_engine/placeholder/manager.py', 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace('def __init__(self, mapping: Dict[str, str] = None, counter: int = 0):', 'def __init__(self, mapping: Dict[str, str] = None, counter: int = 0, glossary_map: Dict[str, str] = None, gl_counter: int = 0):\n        self.glossary_map = glossary_map or {}\n        self.gl_counter = gl_counter')
content = content.replace('self.counter = counter', 'self.counter = counter\n        self.gl_mapping = {}')

protect_new = '''def protect(self, text: str) -> str:
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
                    idx += len(placeholder)'''

content = content.replace('def protect(self, text: str) -> str:\n        protected_text = text', protect_new)

restore_old = '''def restore(self, text: str) -> str:
        restored = text
        
        # We must restore in reverse order (highest counter to lowest) 
        # to properly unpack nested placeholders!
        # e.g., if PH2 contains PH1, we expand PH2 first, which reveals PH1, then we expand PH1.
        
        # Sort by counter descending. The keys are like ⟦PH0⟧, so we extract the int.
        sorted_placeholders = sorted(
            self.mapping.items(), 
            key=lambda item: int(item[0].replace("⟦PH", "").replace("⟧", "")), 
            reverse=True
        )
        
        for ph, raw in sorted_placeholders:
            if ph not in restored:
                raise PlaceholderRestorationError(f"Missing placeholder {ph} in translation.")
            restored = restored.replace(ph, raw)
            
        # Ensure no unexpected placeholders were injected or left behind
        leftover = re.search(r'⟦PH\d+⟧', restored)
        if leftover:
            raise PlaceholderRestorationError(f"Unresolved placeholder found: {leftover.group(0)}")
            
        return restored'''

restore_new = '''def restore(self, text: str) -> str:
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
            
        return restored'''

content = content.replace(restore_old, restore_new)

to_dict_old = '''def to_dict(self) -> Dict[str, Any]:
        return {
            "mapping": self.mapping,
            "counter": self.counter
        }'''

to_dict_new = '''def to_dict(self) -> Dict[str, Any]:
        return {
            "mapping": self.mapping,
            "counter": self.counter,
            "gl_mapping": getattr(self, 'gl_mapping', {}),
            "gl_counter": getattr(self, 'gl_counter', 0)
        }'''
content = content.replace(to_dict_old, to_dict_new)

from_dict_old = '''@classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PlaceholderManager':
        return cls(mapping=data.get("mapping", {}), counter=data.get("counter", 0))'''

from_dict_new = '''@classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PlaceholderManager':
        inst = cls(mapping=data.get("mapping", {}), counter=data.get("counter", 0))
        inst.gl_mapping = data.get("gl_mapping", {})
        inst.gl_counter = data.get("gl_counter", 0)
        return inst'''
content = content.replace(from_dict_old, from_dict_new)

with open('pdf_engine/placeholder/manager.py', 'w', encoding='utf-8') as f:
    f.write(content)
