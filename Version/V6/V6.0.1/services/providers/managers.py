from typing import Dict, List, Optional
from .base.provider import BaseProvider
from .base.capability import ModelCapability

class ProviderManager:
    """Orchestrates AI providers, loads them, and manages switching."""
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ProviderManager, cls).__new__(cls)
            cls._instance.providers: Dict[str, BaseProvider] = {}
            cls._instance.active_provider: Optional[BaseProvider] = None
        return cls._instance
        
    def register_provider(self, provider: BaseProvider) -> None:
        self.providers[provider.provider_name] = provider
        
    def select_active_provider(self, name: str) -> bool:
        if name in self.providers:
            self.active_provider = self.providers[name]
            return True
        return False
        
    def get_active_provider(self) -> Optional[BaseProvider]:
        return self.active_provider
        
    def unload_provider(self, name: str) -> None:
        if name in self.providers:
            if self.active_provider == self.providers[name]:
                self.active_provider = None
            self.providers[name].shutdown()
            del self.providers[name]

class ModelManager:
    """Manages models across all providers and tracks their capabilities."""
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ModelManager, cls).__new__(cls)
            cls._instance.models: Dict[str, ModelCapability] = {}
        return cls._instance
        
    def update_models_from_provider(self, provider: BaseProvider) -> None:
        models = provider.list_models()
        for name, cap in models.items():
            self.models[f"{provider.provider_name}::{name}"] = cap
            
    def get_capabilities(self, fully_qualified_name: str) -> Optional[ModelCapability]:
        return self.models.get(fully_qualified_name)
