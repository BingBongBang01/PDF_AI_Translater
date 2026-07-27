from services.base_service import BaseService
from core.logger import logger
from core.event_bus import EventBus
from services.providers.managers import ProviderManager
from services.translation.chunking.chunker import TextChunker
from services.translation.prompts.prompt_engine import PromptEngine
from services.translation.prompts.glossary import Glossary
from services.translation.pipeline.retry_manager import RetryManager
from services.translation.recovery.translation_memory import TranslationMemory
from services.providers.base.request import TranslationRequest, RetryPolicy
from services.providers.openai_provider import OpenAIProvider
from services.providers.gemini_provider import GeminiProvider
from services.providers.claude_provider import ClaudeProvider
from services.providers.openrouter_provider import OpenRouterProvider
from services.providers.ollama_provider import OllamaProvider
import uuid

class TranslationService(BaseService):
    """Facade for Translation operations."""
    def __init__(self):
        self.provider_manager = ProviderManager()
        self.provider_manager.register_provider(OpenAIProvider())
        self.provider_manager.register_provider(GeminiProvider())
        self.provider_manager.register_provider(ClaudeProvider())
        self.provider_manager.register_provider(OpenRouterProvider())
        self.provider_manager.register_provider(OllamaProvider())
        self.provider_manager.select_active_provider("OpenAI")
        
        self.glossary = Glossary()
        self.prompt_engine = PromptEngine(self.glossary)
        self.chunker = TextChunker()
        self.memory = TranslationMemory()
        self.retry_manager = RetryManager(RetryPolicy())

    def translate(self, text: str, source_lang: str, target_lang: str, stream: bool = False):
        logger.info(f"Translating text from {source_lang} to {target_lang}")
        
        # 1. Check Memory
        cached = self.memory.get_translation(text, source_lang, target_lang)
        if cached:
            EventBus.publish("TranslationFinished", "cache", {"text": cached})
            return cached
            
        # 2. Chunk
        chunks = self.chunker.chunk_text(text, 1)
        
        # 3. Process
        provider = self.provider_manager.get_active_provider()
        if not provider:
            logger.error("No active provider selected")
            return None
            
        full_translation = []
        for chunk in chunks:
            prompt = self.prompt_engine.build_prompt(chunk.text, source_lang, target_lang)
            req = TranslationRequest(
                request_id=str(uuid.uuid4()),
                chunk=chunk,
                prompt=prompt,
                source_language=source_lang,
                target_language=target_lang,
                stream=stream
            )
            
            if stream:
                gen = self.retry_manager.execute_with_retry(provider.stream_translate, req)
                chunk_trans = ""
                for token_str in gen:
                    if isinstance(token_str, str):
                        chunk_trans += token_str
                        EventBus.publish("TranslationStream", req.request_id, token_str)
                full_translation.append(chunk_trans)
            else:
                resp = self.retry_manager.execute_with_retry(provider.translate, req)
                full_translation.append(resp.translated_text)
                
        final_text = " ".join(full_translation)
        
        # 4. Save to Memory
        self.memory.save_translation(text, final_text, source_lang, target_lang)
        
        EventBus.publish("TranslationFinished", "api", {"text": final_text})
        return final_text
