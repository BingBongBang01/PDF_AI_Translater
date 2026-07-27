from typing import Generator
from services.providers.base.provider import BaseProvider
from services.providers.base.request import TranslationRequest
from services.providers.base.response import TranslationResponse
from services.providers.base.capability import ModelCapability
from core.logger import logger
import time

class OpenAIProvider(BaseProvider):
    @property
    def provider_name(self) -> str:
        return "OpenAI"
        
    def authenticate(self) -> bool:
        return True
        
    def health_check(self) -> bool:
        return True
        
    def list_models(self) -> dict[str, ModelCapability]:
        return {
            "gpt-4o": ModelCapability(context_window=128000, supports_streaming=True),
            "gpt-3.5-turbo": ModelCapability(context_window=16385, supports_streaming=True)
        }
        
    def translate(self, request: TranslationRequest) -> TranslationResponse:
        logger.info(f"OpenAI translating chunk {request.chunk.chunk_id}")
        return TranslationResponse(
            request_id=request.request_id,
            chunk_id=request.chunk.chunk_id,
            translated_text=f"[OpenAI Translation of: {request.chunk.text}]",
            finish_reason="stop",
            usage={"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20}
        )
        
    def stream_translate(self, request: TranslationRequest) -> Generator[str, None, TranslationResponse]:
        logger.info(f"OpenAI streaming chunk {request.chunk.chunk_id}")
        yield "[OpenAI "
        yield "Streaming "
        yield f"Translation of: {request.chunk.text}]"
        
        return TranslationResponse(
            request_id=request.request_id,
            chunk_id=request.chunk.chunk_id,
            translated_text=f"[OpenAI Streaming Translation of: {request.chunk.text}]",
            finish_reason="stop",
            usage={"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20}
        )
        
    def estimate_tokens(self, text: str) -> int:
        return len(text) // 4
        
    def count_tokens(self, text: str) -> int:
        return len(text) // 4
        
    def validate_request(self, request: TranslationRequest) -> bool:
        return True
        
    def validate_response(self, response: TranslationResponse) -> bool:
        return True
