import pytest
from services.translation_service import TranslationService
from services.providers.base.request import TranslationChunk

def test_translation_chunking():
    service = TranslationService()
    chunks = service.chunker.chunk_text("Hello world " * 1000, 1)
    assert len(chunks) > 0
    assert len(chunks[0].text) > 0

def test_provider_registration():
    service = TranslationService()
    assert "OpenAI" in service.provider_manager.providers
    assert "Gemini" in service.provider_manager.providers
