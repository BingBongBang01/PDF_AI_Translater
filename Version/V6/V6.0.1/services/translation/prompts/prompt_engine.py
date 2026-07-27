from services.providers.base.request import PromptTemplate, SystemPrompt, UserPrompt
from .glossary import Glossary

class PromptEngine:
    def __init__(self, glossary: Glossary):
        self.glossary = glossary
        self.base_system_prompt = "You are a professional translator. Translate from {source} to {target}."
        
    def build_prompt(self, text: str, source_lang: str, target_lang: str) -> PromptTemplate:
        terms = self.glossary.get_terms_for_text(text)
        system_content = self.base_system_prompt
        
        if terms:
            glossary_str = "\nGlossary:\n" + "\n".join([f"{k} -> {v}" for k, v in terms.items()])
            system_content += glossary_str
            
        sys_prompt = SystemPrompt(content=system_content, variables={"source": source_lang, "target": target_lang})
        user_prompt = UserPrompt(content=text)
        
        return PromptTemplate(system_prompt=sys_prompt, user_prompt=user_prompt)
