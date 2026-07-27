from PySide6.QtCore import Signal
from controllers.base_controller import BaseController
from services.translation_service import TranslationService
from workers.base_worker import BaseWorker

PROVIDER_NAME_MAP = {
    "Google Gemini": "Gemini",
    "OpenAI": "OpenAI",
    "Anthropic": "Claude",
    "Local Runtime": "Ollama",
}


class TranslateWorker(BaseWorker):
    """Runs TranslationService.translate() off the UI thread."""
    result_ready = Signal(str)

    def __init__(self, service: TranslationService, text: str, source_lang: str, target_lang: str, parent=None):
        super().__init__(parent)
        self.service = service
        self.text = text
        self.source_lang = source_lang
        self.target_lang = target_lang

    def run(self):
        try:
            result = self.service.translate(self.text, self.source_lang, self.target_lang)
            self.result_ready.emit(result or "")
            self.finished.emit(True)
        except Exception as e:
            self.error.emit(str(e))


class TranslationController(BaseController):
    """Mediates TranslatePage UI and TranslationService."""
    translation_ready = Signal(str)
    translation_failed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.service = TranslationService()
        self._worker = None

    def select_provider(self, ui_provider_name: str):
        internal_name = PROVIDER_NAME_MAP.get(ui_provider_name, ui_provider_name)
        return self.service.provider_manager.select_active_provider(internal_name)

    def translate_async(self, text: str, source_lang: str, target_lang: str):
        self._worker = TranslateWorker(self.service, text, source_lang, target_lang, self)
        self._worker.result_ready.connect(self.translation_ready.emit)
        self._worker.error.connect(self.translation_failed.emit)
        self._worker.start()

    def stop(self):
        if self._worker and self._worker.isRunning():
            self._worker.terminate()
