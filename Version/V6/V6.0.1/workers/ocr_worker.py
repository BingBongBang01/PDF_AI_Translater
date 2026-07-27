from PySide6.QtCore import Signal
from workers.base_worker import BaseWorker

class ImageLoaderWorker(BaseWorker):
    """Loads images from disk into QImages in the background."""
    image_loaded = Signal(str, object)
    
    def __init__(self, filepaths, parent=None):
        super().__init__(parent)
        self.filepaths = filepaths
        
    def run(self):
        from PySide6.QtGui import QImage
        try:
            for path in self.filepaths:
                img = QImage(path)
                if not img.isNull():
                    self.image_loaded.emit(path, img)
            self.finished.emit(True)
        except Exception as e:
            self.error.emit(str(e))

class ThumbnailWorker(BaseWorker):
    """Generates low-res thumbnails from paths."""
    thumbnail_ready = Signal(str, object)
    
    def __init__(self, filepaths, size=(120, 160), parent=None):
        super().__init__(parent)
        self.filepaths = filepaths
        self.size = size
        
    def run(self):
        from PySide6.QtGui import QImage
        from PySide6.QtCore import Qt
        try:
            for path in self.filepaths:
                img = QImage(path)
                if not img.isNull():
                    thumb = img.scaled(self.size[0], self.size[1], Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    self.thumbnail_ready.emit(path, thumb)
            self.finished.emit(True)
        except Exception as e:
            self.error.emit(str(e))

class PreviewWorker(BaseWorker):
    """Generates high resolution preview for central view."""
    preview_ready = Signal(str, object)
    
    def __init__(self, filepath, parent=None):
        super().__init__(parent)
        self.filepath = filepath
        
    def run(self):
        from PySide6.QtGui import QImage
        try:
            img = QImage(self.filepath)
            self.preview_ready.emit(self.filepath, img)
            self.finished.emit(True)
        except Exception as e:
            self.error.emit(str(e))

class OCRWorker(BaseWorker):
    """Placeholder worker for OCR engine execution."""
    ocr_result = Signal(str, dict) # filepath, result_data
    
    def __init__(self, filepath, settings, parent=None):
        super().__init__(parent)
        self.filepath = filepath
        self.settings = settings
        
    def run(self):
        # Placeholder OCR logic
        self.ocr_result.emit(self.filepath, {"text": "Placeholder OCR result", "confidence": 0.95})
        self.finished.emit(True)

class ValidationWorker(BaseWorker):
    """Validates OCR results for common errors."""
    validation_done = Signal(str, list)
    
    def __init__(self, result_data, parent=None):
        super().__init__(parent)
        self.result_data = result_data
        
    def run(self):
        warnings = []
        if self.result_data.get("confidence", 1.0) < 0.8:
            warnings.append("Low confidence detected.")
        if not self.result_data.get("text"):
            warnings.append("Empty region.")
        self.validation_done.emit("placeholder_id", warnings)
        self.finished.emit(True)
