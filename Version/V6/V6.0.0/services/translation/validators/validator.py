from typing import List

class BaseValidator:
    def validate(self, original_text: str, translated_text: str) -> List[str]:
        raise NotImplementedError

class StructureValidator(BaseValidator):
    """Validates markdown/HTML structures are preserved."""
    def validate(self, original_text: str, translated_text: str) -> List[str]:
        errors = []
        if original_text.count("```") != translated_text.count("```"):
            errors.append("Code block markdown mismatch.")
        if original_text.count("#") != translated_text.count("#"):
            errors.append("Header structure mismatch.")
        return errors

class ContentValidator(BaseValidator):
    """Checks for empty or anomalously short translations."""
    def validate(self, original_text: str, translated_text: str) -> List[str]:
        errors = []
        if not translated_text.strip():
            errors.append("Empty translation returned.")
        elif len(translated_text) < len(original_text) * 0.1:
            errors.append("Translation is suspiciously short.")
        return errors
