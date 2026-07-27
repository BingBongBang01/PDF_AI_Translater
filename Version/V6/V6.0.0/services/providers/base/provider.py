from typing import List, Generator, Any
from .request import TranslationRequest
from .response import TranslationResponse
from .capability import ModelCapability

class BaseProvider:
    """Interface that every AI Provider must implement."""
    
    @property
    def provider_name(self) -> str:
        raise NotImplementedError
        
    def initialize(self, config: dict) -> None:
        pass
        
    def authenticate(self) -> bool:
        raise NotImplementedError
        
    def health_check(self) -> bool:
        raise NotImplementedError
        
    def list_models(self) -> dict[str, ModelCapability]:
        raise NotImplementedError
        
    def translate(self, request: TranslationRequest) -> TranslationResponse:
        raise NotImplementedError
        
    def stream_translate(self, request: TranslationRequest) -> Generator[str, None, TranslationResponse]:
        raise NotImplementedError
        
    def cancel(self) -> None:
        pass
        
    def estimate_tokens(self, text: str) -> int:
        raise NotImplementedError
        
    def count_tokens(self, text: str) -> int:
        raise NotImplementedError
        
    def validate_request(self, request: TranslationRequest) -> bool:
        raise NotImplementedError
        
    def validate_response(self, response: TranslationResponse) -> bool:
        raise NotImplementedError
        
    def shutdown(self) -> None:
        pass
