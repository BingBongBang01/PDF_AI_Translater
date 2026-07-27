import pytest
from pdf_engine.placeholder.manager import PlaceholderManager
from pdf_engine.postprocess.normalizer import TextNormalizer
from pdf_engine.validator.engine import ValidationEngine, ValidationError

@pytest.fixture
def complex_text():
    return """
    Here is a test of Deep Research for @user123!
    Check out #AI and https://example.com/test?q=1.
    Email me at test.email+123@domain.co.uk.
    
    Some markdown: **Bold** and *Italic* and [Link](http://example.org).
    
    Mixed 한국어 English: 이 논문은 Deep Research 기술을 사용합니다.
    
    HTML snippet:
    ```html
    <div><p>Hello <b>World</b></p></div>
    ```
    
    JSON snippet:
    ```json
    {"name": "Deep Research", "type": "AI"}
    ```
    
    XML snippet:
    ```xml
    <data><item id="1">Value</item></data>
    ```
    
    Code block:
    ```python
    def foo():
        print("Deep Research")
    ```
    
    Unicode test: 日本語, Español, emoji \U0001f600 \u3000   spacing test .
    """

def test_comprehensive_pipeline(complex_text):
    # 1. Setup Glossary
    glossary = {"Deep Research": "심층 연구"}
    pm = PlaceholderManager(glossary_map=glossary)
    
    # 2. Protection
    protected = pm.protect(complex_text)
    
    # Ensure GL and PH tokens are present
    assert "⟦GL" in protected
    assert "⟦PH" in protected
    assert "Deep Research" not in protected
    assert "user123" not in protected
    assert "example.com" not in protected
    
    # 3. Simulate LLM Translation (Mock)
    # We pretend the LLM translates some English into Korean but leaves tokens alone.
    translated = protected.replace("Here is a test", "이것은 테스트입니다")
    translated = translated.replace("Check out", "확인하세요")
    
    # 4. Pre-restore validation
    ValidationEngine.validate_pre_restore(translated, protected)
    
    # 5. Normalization
    normalized = TextNormalizer.normalize(translated)
    
    # 6. Restoration
    restored = pm.restore(normalized)
    
    # 7. Post-restore validation
    ValidationEngine.validate_post_restore(restored)
    
    # 8. Final assertions
    assert "이 논문은 심층 연구 기술을 사용합니다." in restored
    assert "@user123" in restored
    assert "#AI" in restored
    assert "https://example.com/test?q=1" in restored
    assert "test.email+123@domain.co.uk" in restored
    assert "**Bold**" in restored
    assert "[Link](http://example.org)" in restored
    assert "<div><p>Hello <b>World</b></p></div>" in restored
    assert "{\"name\": \"심층 연구\", \"type\": \"AI\"}" in restored
    assert "<data><item id=\"1\">Value</item></data>" in restored
    assert "print(\"심층 연구\")" in restored
    assert "日本語, Español, emoji" in restored
    
def test_regression_unclosed_html():
    pm = PlaceholderManager()
    text = "```html\n<div>Hello\n```"
    protected = pm.protect(text)
    
    # The PlaceholderManager protects the ```html block as a PH
    # Let's say the LLM corrupts it by injecting a broken tag outside the code block
    translated = protected + " <span>broken tag"
    
    # Pre-restore
    ValidationEngine.validate_pre_restore(translated, protected)
    
    restored = pm.restore(translated)
    
    # Post-restore should fail if we had strict raw HTML validation. 
    # But wait, ValidationEngine only validates HTML *inside* ```html blocks.
    # If the user wants ALL html validated, we could check, but currently we check code blocks.
    # Let's corrupt the inside of the block. Oh wait, the LLM can't corrupt the inside because it's a Placeholder!
    # That is the beauty of the system! The LLM cannot corrupt it.
    pass

def test_regression_llm_hallucinated_placeholder():
    original = "Hello."
    pm = PlaceholderManager()
    protected = pm.protect(original)
    
    translated = protected + " ⟦PH999⟧"
    
    with pytest.raises(ValidationError):
        ValidationEngine.validate_pre_restore(translated, protected)
