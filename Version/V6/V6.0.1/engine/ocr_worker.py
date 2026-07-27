from PySide6.QtCore import QRunnable, QObject, Signal
from core.event_bus import EventBus
from core.logger import logger
from engine.ocr_plugins import BaseOCRPlugin
from engine.ocr_preprocessing import OCRPreprocessor
import cv2
import numpy as np

class OCRWorkerSignals(QObject):
    finished = Signal(str, list)
    error = Signal(str, str)

class OCRWorker(QRunnable):
    def __init__(self, job_id: str, image_path: str, lang: str, plugin: BaseOCRPlugin):
        super().__init__()
        self.job_id = job_id
        self.image_path = image_path
        self.lang = lang
        self.plugin = plugin
        self.signals = OCRWorkerSignals()

    def run(self):
        try:
            EventBus.publish("OCRStarted", self.job_id)
            
            # 1. Load image
            img = cv2.imdecode(np.fromfile(self.image_path, dtype=np.uint8), cv2.IMREAD_COLOR)
            if img is None:
                raise ValueError(f"Failed to load image from {self.image_path}")

            # 2. Preprocess
            preprocessed = OCRPreprocessor.preprocess(img, deskew=True, denoise=True)
            
            # 3. Recognize
            results = self.plugin.recognize(preprocessed, self.lang)
            
            # 4. Return results
            self.signals.finished.emit(self.job_id, results)
            EventBus.publish("OCRFinished", self.job_id, {"results": len(results)})
            
        except Exception as e:
            logger.error(f"OCR Worker Error on job {self.job_id}: {e}")
            self.signals.error.emit(self.job_id, str(e))
            EventBus.publish("OCRFailed", self.job_id, str(e))
