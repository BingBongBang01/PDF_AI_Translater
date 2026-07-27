from PySide6.QtCore import Signal
from workers.base_worker import BaseWorker
from services.providers.base.request import TranslationRequest
from services.providers.managers import ProviderManager

class ProviderWorker(BaseWorker):
    """Executes standard blocking translation requests."""
    result_ready = Signal(str, object) # request_id, TranslationResponse
    
    def __init__(self, request: TranslationRequest, parent=None):
        super().__init__(parent)
        self.request = request
        
    def run(self):
        try:
            provider = ProviderManager().get_active_provider()
            if not provider:
                raise ValueError("No active provider selected.")
                
            response = provider.translate(self.request)
            self.result_ready.emit(self.request.request_id, response)
            self.finished.emit(True)
        except Exception as e:
            self.error.emit(str(e))

class StreamingWorker(BaseWorker):
    """Executes streaming translation requests."""
    chunk_received = Signal(str, str) # request_id, text_chunk
    stream_complete = Signal(str, object) # request_id, TranslationResponse
    
    def __init__(self, request: TranslationRequest, parent=None):
        super().__init__(parent)
        self.request = request
        self.is_cancelled = False
        
    def run(self):
        try:
            provider = ProviderManager().get_active_provider()
            if not provider:
                raise ValueError("No active provider selected.")
                
            stream = provider.stream_translate(self.request)
            response = None
            
            while not self.is_cancelled:
                try:
                    chunk = next(stream)
                    self.chunk_received.emit(self.request.request_id, chunk)
                except StopIteration as e:
                    response = e.value
                    break
                    
            if not self.is_cancelled and response:
                self.stream_complete.emit(self.request.request_id, response)
            self.finished.emit(not self.is_cancelled)
        except Exception as e:
            self.error.emit(str(e))
            
    def cancel(self):
        self.is_cancelled = True
        provider = ProviderManager().get_active_provider()
        if provider:
            provider.cancel()

class RetryWorker(BaseWorker):
    """Handles exponential backoff retry logic for failed requests."""
    retry_attempted = Signal(str, int)
    
    def run(self):
        pass # Placeholder for retry logic

class HealthWorker(BaseWorker):
    """Periodically checks provider health status."""
    health_status = Signal(str, bool)
    
    def run(self):
        pass # Placeholder for pinging provider API endpoints

class TokenWorker(BaseWorker):
    """Estimates and counts tokens without blocking UI."""
    token_count = Signal(str, int)
    
    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        self.text = text
        
    def run(self):
        try:
            provider = ProviderManager().get_active_provider()
            if provider:
                count = provider.count_tokens(self.text)
                self.token_count.emit("dummy_id", count)
            self.finished.emit(True)
        except Exception as e:
            self.error.emit(str(e))
