import pytest
from pdf_engine.postprocess.normalizer import TextNormalizer

def test_spacing_normalization():
    # Multiple spaces and spaces before punctuation
    text = "Hello    world , this is a test  ! "
    normalized = TextNormalizer.normalize(text)
    assert normalized == "Hello world, this is a test!"

def test_quotes_normalization():
    # Smart quotes to standard
    text = "“Hello” and ‘World’"
    normalized = TextNormalizer.normalize(text)
    assert normalized == "\"Hello\" and 'World'"

def test_line_breaks():
    # Triple line break to double
    text = "Line 1\n\n\n\nLine 2"
    normalized = TextNormalizer.normalize(text)
    assert normalized == "Line 1\n\nLine 2"

def test_capitalization():
    text = "this is a test. it is good! why not?"
    normalized = TextNormalizer.normalize(text)
    assert normalized == "this is a test. It is good! Why not?"

def test_safe_unicode_with_placeholders():
    # Ensure NFKC and capitalization doesn't corrupt ⟦PH0⟧
    text = "here is a token ⟦PH0⟧ . it should be safe."
    normalized = TextNormalizer.normalize(text)
    # The space before the period should be removed, and 'it' capitalized.
    assert normalized == "here is a token ⟦PH0⟧. It should be safe."
