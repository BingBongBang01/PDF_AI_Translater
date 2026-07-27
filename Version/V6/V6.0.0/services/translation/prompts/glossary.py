from typing import Dict

class Glossary:
    def __init__(self):
        self.terms: Dict[str, str] = {}
        
    def add_term(self, source: str, target: str):
        self.terms[source] = target
        
    def get_terms_for_text(self, text: str) -> Dict[str, str]:
        return {s: t for s, t in self.terms.items() if s in text}
