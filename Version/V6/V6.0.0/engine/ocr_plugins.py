from typing import Dict, Any, List, Tuple
from abc import ABC, abstractmethod
from core.logger import logger
from core.exceptions import PluginError
import numpy as np

class OCRResult:
    def __init__(self, text: str, bbox: Tuple[int, int, int, int], confidence: float):
        self.text = text
        self.bbox = bbox
        self.confidence = confidence

class BaseOCRPlugin(ABC):
    def __init__(self, name: str):
        self.name = name
        
    @abstractmethod
    def load_model(self, lang: str) -> bool:
        pass
        
    @abstractmethod
    def recognize(self, image: np.ndarray, lang: str) -> List[OCRResult]:
        pass

class TesseractPlugin(BaseOCRPlugin):
    def __init__(self):
        super().__init__("Tesseract")
        
    def load_model(self, lang: str) -> bool:
        logger.info(f"TesseractPlugin initialized for {lang}")
        return True
        
    def recognize(self, image: np.ndarray, lang: str) -> List[OCRResult]:
        return [OCRResult("tesseract_stub", (0, 0, 100, 100), 0.9)]

class EasyOCRPlugin(BaseOCRPlugin):
    def __init__(self):
        super().__init__("EasyOCR")
        self.reader = None
        
    def load_model(self, lang: str) -> bool:
        logger.info(f"EasyOCRPlugin initialized for {lang}")
        return True
        
    def recognize(self, image: np.ndarray, lang: str) -> List[OCRResult]:
        return [OCRResult("easyocr_stub", (0, 0, 100, 100), 0.95)]

class PaddleOCRPlugin(BaseOCRPlugin):
    def __init__(self):
        super().__init__("PaddleOCR")
        self.model = None
        
    def load_model(self, lang: str) -> bool:
        logger.info(f"PaddleOCRPlugin initialized for {lang}")
        return True
        
    def recognize(self, image: np.ndarray, lang: str) -> List[OCRResult]:
        return [OCRResult("paddleocr_stub", (0, 0, 100, 100), 0.98)]
