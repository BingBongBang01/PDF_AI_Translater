from typing import Generator
from services.providers.base.provider import BaseProvider
from services.providers.base.request import TranslationRequest
from services.providers.base.response import TranslationResponse
from services.providers.base.capability import ModelCapability
from core.logger import logger

class GeminiProvider(BaseProvider):
    @property
    def provider_name(self) -> str:
        return "Gemini"
        
    def authenticate(self) -> bool:
        return True
        
    def health_check(self) -> bool:
        return True
        
    def list_models(self) -> dict[str, ModelCapability]:
        return {
            "gemini-1.5-pro": ModelCapability(context_window=2000000, supports_streaming=True)
        }
        
    def translate(self, request: TranslationRequest) -> TranslationResponse:
        return TranslationResponse(request.request_id, request.chunk.chunk_id, f"[Gemini: {request.chunk.text}]", "stop", {})
        
    def stream_translate(self, request: TranslationRequest) -> Generator[str, None, TranslationResponse]:
        yield "[Gemini Stream] "
        return TranslationResponse(request.request_id, request.chunk.chunk_id, f"[Gemini Stream: {request.chunk.text}]", "stop", {})
        
    def estimate_tokens(self, text: str) -> int:
        return len(text) // 4
        
    def count_tokens(self, text: str) -> int:
        return len(text) // 4
        
    def validate_request(self, request: TranslationRequest) -> bool: return True
    def validate_response(self, response: TranslationResponse) -> bool: return True
