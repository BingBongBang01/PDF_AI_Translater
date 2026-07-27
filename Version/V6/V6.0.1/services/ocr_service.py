from services.base_service import BaseService
from core.logger import logger
from engine.ocr_engine import OCREngine

class OCRService(BaseService):
    """Facade for OCR operations, backed by OCREngine."""
    def __init__(self):
        self.engine = OCREngine()

    def perform_ocr(self, image_path: str, lang: str):
        logger.info(f"Performing OCR on {image_path} with lang {lang}")
        return self.engine.enqueue_image(image_path, lang)
        
    def set_engine(self, engine_name: str, lang: str = "eng"):
        self.engine.set_engine(engine_name, lang)
