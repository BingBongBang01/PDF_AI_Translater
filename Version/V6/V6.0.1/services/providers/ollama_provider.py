from typing import Generator
from services.providers.base.provider import BaseProvider
from services.providers.base.request import TranslationRequest
from services.providers.base.response import TranslationResponse
from services.providers.base.capability import ModelCapability

class OllamaProvider(BaseProvider):
    @property
    def provider_name(self) -> str: return "Ollama"
    def authenticate(self) -> bool: return True
    def health_check(self) -> bool: return True
    def list_models(self) -> dict[str, ModelCapability]:
        return {"llama3": ModelCapability(context_window=8192, supports_streaming=True)}
    def translate(self, request: TranslationRequest) -> TranslationResponse:
        return TranslationResponse(request.request_id, request.chunk.chunk_id, f"[Ollama: {request.chunk.text}]", "stop", {})
    def stream_translate(self, request: TranslationRequest) -> Generator[str, None, TranslationResponse]:
        yield "[Ollama Stream] "
        return TranslationResponse(request.request_id, request.chunk.chunk_id, f"[Ollama Stream: {request.chunk.text}]", "stop", {})
    def estimate_tokens(self, text: str) -> int: return len(text) // 4
    def count_tokens(self, text: str) -> int: return len(text) // 4
    def validate_request(self, request: TranslationRequest) -> bool: return True
    def validate_response(self, response: TranslationResponse) -> bool: return True
