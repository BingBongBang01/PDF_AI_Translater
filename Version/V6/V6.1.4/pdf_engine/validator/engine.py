import re
import json
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pdf_engine.logger import get_logger
from pdf_engine.placeholder.segment import Segment

class StrictHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []
        self.error = None

    def handle_starttag(self, tag, attrs):
        # Void elements that don't need closing
        if tag not in ['area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr']:
            self.tags.append(tag)

    def handle_endtag(self, tag):
        if not self.tags:
            self.error = f"Closing tag </{tag}> without matching start tag."
            return
        if self.tags[-1] != tag:
            self.error = f"Mismatched closing tag: expected </{self.tags[-1]}>, got </{tag}>."
            return
        self.tags.pop()

class ValidationError(Exception):
    pass

class ValidationEngine:
    """Validates segments for placeholder integrity and syntax formats."""

    @classmethod
    def validate_pre_restore(cls, translated_text: str, original_text: str):
        """Checks for duplicated or missing placeholders before restoration."""
        # Find all PH and GL tokens in original and translated
        orig_tokens = re.findall(r'⟦(?:PH|GL)\d+⟧', original_text)
        trans_tokens = re.findall(r'⟦(?:PH|GL)\d+⟧', translated_text)
        
        orig_counts = {}
        for t in orig_tokens:
            orig_counts[t] = orig_counts.get(t, 0) + 1
            
        trans_counts = {}
        for t in trans_tokens:
            trans_counts[t] = trans_counts.get(t, 0) + 1
            
        # Check missing or duplicated
        for token, count in orig_counts.items():
            t_count = trans_counts.get(token, 0)
            if t_count < count:
                raise ValidationError(f"Missing placeholder: {token} was dropped by LLM.")
            if t_count > count:
                raise ValidationError(f"Duplicated placeholder: {token} appears {t_count} times, expected {count}.")

        # Check hallucinations
        for token in trans_counts:
            if token not in orig_counts:
                raise ValidationError(f"Hallucinated placeholder: {token} was not in original text.")

    @classmethod
    def validate_post_restore(cls, restored_text: str):
        """Checks syntax format of the final text."""
        # 1. Unresolved tokens
        leftover = re.search(r'⟦(?:PH|GL)\d+⟧', restored_text)
        if leftover:
            raise ValidationError(f"Unresolved placeholder leaked into output: {leftover.group(0)}")
            
        # 2. JSON validation
        json_blocks = re.findall(r'```json\s*(.*?)\s*```', restored_text, re.DOTALL)
        for block in json_blocks:
            try:
                json.loads(block)
            except json.JSONDecodeError as e:
                raise ValidationError(f"Invalid JSON block: {e}")

        # 3. XML validation
        xml_blocks = re.findall(r'```xml\s*(.*?)\s*```', restored_text, re.DOTALL)
        for block in xml_blocks:
            try:
                ET.fromstring(f"<root>{block}</root>")
            except ET.ParseError as e:
                raise ValidationError(f"Invalid XML block: {e}")

        # 4. HTML validation
        html_blocks = re.findall(r'```html\s*(.*?)\s*```', restored_text, re.DOTALL)
        for block in html_blocks:
            parser = StrictHTMLParser()
            parser.feed(block)
            if parser.error:
                raise ValidationError(f"Invalid HTML block: {parser.error}")
            if parser.tags:
                raise ValidationError(f"Invalid HTML block: Unclosed tags {parser.tags}")

        # 5. Markdown validation (detect broken links or unclosed emphasis)
        # Check for hanging links like [text](url without closing paren
        if re.search(r'\[[^\]]+\]\([^)]+(?!\))(?=\s|$)', restored_text):
            raise ValidationError("Invalid Markdown: Unclosed link parenthesis.")
            
        # Check for mismatched bold/italic asterisks (basic heuristic)
        asterisks = restored_text.count('*')
        if asterisks % 2 != 0:
            # Not strictly an error if they use a literal asterisk, but usually indicates broken markdown
            # Only fail if we are strictly validating markdown. Let's make it a warning instead of abort.
            get_logger().log("[WARNING] Possible unclosed Markdown emphasis (odd number of asterisks).")
