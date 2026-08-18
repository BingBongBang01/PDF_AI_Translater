import unicodedata
import re

class TextNormalizer:
    """Intelligently normalizes LLM translated text before placeholder restoration."""
    
    @staticmethod
    def normalize(text: str) -> str:
        if not text:
            return text
            
        # 1. Unicode Normalization (NFKC standardizes fullwidth alphanumerics, etc.)
        # Wait, NFKC might normalize our strict token brackets \u27e6 and \u27e7 into something else!
        # Let's check: unicodedata.normalize('NFKC', '\u27e6PH0\u27e7')
        # \u27e6 is MATHEMATICAL LEFT WHITE SQUARE BRACKET. It does NOT decompose in NFKC!
        normalized = unicodedata.normalize('NFKC', text)
        
        # 2. Normalize Quotes (Smart quotes to standard)
        normalized = normalized.replace('“', '"').replace('”', '"')
        normalized = normalized.replace('‘', "'").replace('’', "'")
        
        # 3. Normalize Parentheses (Full-width to half-width already handled by NFKC, but just in case)
        normalized = normalized.replace('（', '(').replace('）', ')')
        
        # 4. Spacing
        # Collapse multiple spaces into one
        normalized = re.sub(r'[ \t]+', ' ', normalized)
        # Remove spaces before punctuation
        normalized = re.sub(r' ([.,!?])', r'\1', normalized)
        
        # 5. Line Breaks
        # Replace multiple consecutive linebreaks with a maximum of two
        normalized = re.sub(r'\n{3,}', '\n\n', normalized)
        
        # 6. Capitalization
        # Simple heuristic: capitalize first letter of a sentence
        # (Be careful with placeholders like ⟦PH0⟧, we shouldn't capitalize inside them)
        # We can capitalize the very first character if it's a letter
        def capitalize_match(m):
            return m.group(1) + m.group(2).upper()
            
        # Capitalize after sentence-ending punctuation followed by space
        normalized = re.sub(r'([.!?]\s+)([a-z])', capitalize_match, normalized)
        
        return normalized.strip()
