import json
import pytest
from unittest.mock import patch, MagicMock

from pdf_engine.preprocess.context import ContextDetector
from pdf_engine.placeholder.segment import Segment

@pytest.fixture
def sample_segments():
    return [
        Segment(seg_id="s1", page=0, bbox=(0,0,10,10), text="A Deep Learning approach to AI.", font_size=12, color="#000000", bold=True, needs_translation=True),
        Segment(seg_id="s2", page=0, bbox=(0,10,10,20), text="In this paper, we explore...", font_size=10, color="#000000", bold=False, needs_translation=True)
    ]

@patch("pdf_engine.preprocess.context.call_llm")
def test_context_detection_academic(mock_call_llm, sample_segments):
    # Mock the LLM to return 'academic paper'
    mock_call_llm.return_value = '{"context": "academic paper"}'
    
    # Mock pool entry
    entry = MagicMock()
    entry.provider = "openai"
    entry.model = "gpt-4"
    pool = [entry]
    
    detected = ContextDetector.detect(pool, sample_segments)
    
    assert detected == "academic paper"
    mock_call_llm.assert_called_once()
    
    # Verify prompt contains the sample text
    _, kwargs = mock_call_llm.call_args
    assert "In this paper" in kwargs["user_prompt"]

@patch("pdf_engine.preprocess.context.call_llm")
def test_context_detection_fallback(mock_call_llm, sample_segments):
    # Mock the LLM to return an unknown context
    mock_call_llm.return_value = '{"context": "some unknown category"}'
    
    entry = MagicMock()
    entry.provider = "openai"
    pool = [entry]
    
    detected = ContextDetector.detect(pool, sample_segments)
    
    # Should fallback to 'default' if it doesn't match the strict category list
    assert detected == "default"

def test_context_detection_no_text():
    pool = [MagicMock()]
    segments = []
    
    detected = ContextDetector.detect(pool, segments)
    
    # Should default out early
    assert detected == "default"
