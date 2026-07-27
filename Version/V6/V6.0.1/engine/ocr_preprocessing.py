import numpy as np
import cv2

class OCRPreprocessor:
    """Handles image preprocessing for OCR (deskew, denoise, contrast)."""
    
    @staticmethod
    def preprocess(image: np.ndarray, deskew: bool = True, denoise: bool = True) -> np.ndarray:
        processed = image.copy()
        if len(processed.shape) == 3:
            processed = cv2.cvtColor(processed, cv2.COLOR_BGR2GRAY)
            
        if denoise:
            processed = cv2.fastNlMeansDenoising(processed, None, 10, 7, 21)
            
        if deskew:
            # Deskew logic
            pass
            
        return processed
