import pytest
from pdf_engine.placeholder.manager import PlaceholderManager, PlaceholderRestorationError

def test_protect_urls():
    pm = PlaceholderManager()
    text = "Visit https://google.com for info."
    protected = pm.protect(text)
    assert "⟦PH0⟧" in protected
    assert "https://google.com" not in protected
    assert pm.restore(protected) == text

def test_protect_emails():
    pm = PlaceholderManager()
    text = "Contact me at admin@test.com!"
    protected = pm.protect(text)
    assert "⟦PH0⟧" in protected
    assert pm.restore(protected) == text

def test_nested_placeholders():
    pm = PlaceholderManager()
    # Markdown bold around a link. 
    # Link should be PH0, Bold should be PH1.
    text = "**bold [link](https://example.com)**"
    protected = pm.protect(text)
    assert protected == "⟦PH1⟧"
    assert "⟦PH1⟧" in pm.mapping
    assert pm.restore(protected) == text

def test_serialization():
    pm1 = PlaceholderManager()
    text = "Hey @user check out #python"
    protected = pm1.protect(text)
    
    # Serialize
    data = pm1.to_dict()
    
    # Deserialize
    pm2 = PlaceholderManager.from_dict(data)
    assert pm2.restore(protected) == text
    assert pm2.counter == pm1.counter
    assert pm2.mapping == pm1.mapping

def test_restoration_error_missing():
    pm = PlaceholderManager()
    text = "Here is a [link](https://example.com)."
    protected = pm.protect(text)
    
    # LLM dropped the placeholder!
    corrupted_translated = "Here is a link."
    
    with pytest.raises(PlaceholderRestorationError, match="Missing placeholder"):
        pm.restore(corrupted_translated)

def test_restoration_error_leftover():
    pm = PlaceholderManager()
    text = "Hello world"
    protected = pm.protect(text) # Nothing happens
    
    # LLM hallucinated a placeholder!
    corrupted_translated = "Hello ⟦PH99⟧ world"
    
    with pytest.raises(PlaceholderRestorationError, match="Unresolved placeholder found"):
        pm.restore(corrupted_translated)
