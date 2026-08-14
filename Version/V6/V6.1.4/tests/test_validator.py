import pytest
from pdf_engine.validator.engine import ValidationEngine, ValidationError

def test_missing_placeholder():
    original = "Click here: ⟦PH0⟧ and here: ⟦PH1⟧."
    translated = "여기를 클릭: ⟦PH0⟧"
    with pytest.raises(ValidationError, match="Missing placeholder"):
        ValidationEngine.validate_pre_restore(translated, original)

def test_duplicated_placeholder():
    original = "Click here: ⟦PH0⟧."
    translated = "클릭: ⟦PH0⟧ 그리고 또 클릭 ⟦PH0⟧."
    with pytest.raises(ValidationError, match="Duplicated placeholder"):
        ValidationEngine.validate_pre_restore(translated, original)

def test_hallucinated_placeholder():
    original = "Hello."
    translated = "안녕 ⟦PH0⟧."
    with pytest.raises(ValidationError, match="Hallucinated placeholder"):
        ValidationEngine.validate_pre_restore(translated, original)

def test_valid_json():
    text = "Here is the data: ```json\n{\"key\": \"value\"}\n```"
    ValidationEngine.validate_post_restore(text)

def test_invalid_json():
    text = "Here is the data: ```json\n{\"key\": \"value\"\n```"
    with pytest.raises(ValidationError, match="Invalid JSON block"):
        ValidationEngine.validate_post_restore(text)

def test_valid_html():
    text = "```html\n<div><p>Hello</p><br></div>\n```"
    ValidationEngine.validate_post_restore(text)

def test_invalid_html():
    text = "```html\n<div><p>Hello</div>\n```"
    with pytest.raises(ValidationError, match="Invalid HTML block"):
        ValidationEngine.validate_post_restore(text)

def test_unresolved_placeholder():
    text = "This token was never replaced: ⟦GL0⟧."
    with pytest.raises(ValidationError, match="Unresolved placeholder leaked"):
        ValidationEngine.validate_post_restore(text)

def test_invalid_markdown_link():
    text = "Check out this [link](http://example.com without closing."
    with pytest.raises(ValidationError, match="Invalid Markdown: Unclosed link parenthesis."):
        ValidationEngine.validate_post_restore(text)
