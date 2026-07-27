from PySide6.QtCore import Signal
from controllers.base_controller import BaseController
from services.ocr_service import OCRService
from workers.base_worker import BaseWorker


class OCRRunWorker(BaseWorker):
    """Runs a single-image OCR pass off the UI thread."""
    result_ready = Signal(list)  # List[OCRResult]

    def __init__(self, service: OCRService, image_path: str, lang: str, parent=None):
        super().__init__(parent)
        self.service = service
        self.image_path = image_path
        self.lang = lang

    def run(self):
        import cv2
        try:
            image = cv2.imread(self.image_path)
            if image is None:
                raise ValueError(f"Could not read image: {self.image_path}")

            engine = self.service.engine
            plugin = engine.plugins[engine.current_plugin]
            results = plugin.recognize(image, self.lang)
            self.result_ready.emit(results)
            self.finished.emit(True)
        except Exception as e:
            self.error.emit(str(e))


class OCRController(BaseController):
    """Mediates OCRPage UI and OCRService."""
    ocr_ready = Signal(list)
    ocr_failed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.service = OCRService()
        self._worker = None

    def set_engine(self, engine_name: str, lang: str = "eng"):
        self.service.set_engine(engine_name, lang)

    def run_async(self, image_path: str, lang: str):
        self._worker = OCRRunWorker(self.service, image_path, lang, self)
        self._worker.result_ready.connect(self.ocr_ready.emit)
        self._worker.error.connect(self.ocr_failed.emit)
        self._worker.start()

    def stop(self):
        if self._worker and self._worker.isRunning():
            self._worker.terminate()
