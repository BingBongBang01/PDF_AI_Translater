import os
from PySide6.QtCore import Signal, QObject
from workers.base_worker import BaseWorker

try:
    import fitz  # PyMuPDF
    HAS_PYMUPDF = True
except ImportError:
    HAS_PYMUPDF = False

class ThumbnailWorker(BaseWorker):
    """Generates thumbnails in the background with lazy loading support."""
    thumbnail_ready = Signal(int, object) # page_number, QImage
    
    def __init__(self, filepath, page_list=None, parent=None):
        super().__init__(parent)
        self.filepath = filepath
        self.page_list = page_list # List of specific pages to render, or None for all
        self.is_cancelled = False
        
    def run(self):
        if not HAS_PYMUPDF:
            self.error.emit("PyMuPDF not installed")
            return
            
        try:
            doc = fitz.open(self.filepath)
            pages_to_render = self.page_list if self.page_list is not None else range(len(doc))
            
            for pno in pages_to_render:
                if self.is_cancelled:
                    break
                page = doc.load_page(pno)
                pix = page.get_pixmap(matrix=fitz.Matrix(0.2, 0.2)) # low res thumbnail
                
                from PySide6.QtGui import QImage
                img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888)
                self.thumbnail_ready.emit(pno, img.copy()) # copy is required for thread safety
                self.msleep(10) # Prevent event loop flooding
                
            doc.close()
            self.finished.emit(True)
        except Exception as e:
            self.error.emit(str(e))
            
    def cancel(self):
        self.is_cancelled = True

class MetadataWorker(BaseWorker):
    """Extracts PDF metadata."""
    metadata_ready = Signal(dict)
    
    def __init__(self, filepath, parent=None):
        super().__init__(parent)
        self.filepath = filepath
        
    def run(self):
        if not HAS_PYMUPDF:
            self.error.emit("PyMuPDF not installed")
            return
            
        try:
            doc = fitz.open(self.filepath)
            meta = doc.metadata
            info = {
                "Filename": os.path.basename(self.filepath),
                "Location": self.filepath,
                "Page Count": len(doc),
                "File Size": f"{os.path.getsize(self.filepath) / (1024*1024):.2f} MB",
                "PDF Version": "Unknown", # Optional logic
                "Creator": meta.get("creator", ""),
                "Producer": meta.get("producer", ""),
                "Creation Date": meta.get("creationDate", ""),
                "Modification Date": meta.get("modDate", ""),
                "Encrypted": doc.is_encrypted,
                "Language": "auto" # Could try to guess or read metadata
            }
            doc.close()
            self.metadata_ready.emit(info)
            self.finished.emit(True)
        except Exception as e:
            self.error.emit(str(e))
            
class PreviewWorker(BaseWorker):
    """Generates high resolution preview for central view."""
    preview_ready = Signal(int, object)
    
    def __init__(self, filepath, page_number, zoom=1.0, parent=None):
        super().__init__(parent)
        self.filepath = filepath
        self.page_number = page_number
        self.zoom = zoom
        
    def run(self):
        if not HAS_PYMUPDF:
            self.error.emit("PyMuPDF not installed")
            return
            
        try:
            doc = fitz.open(self.filepath)
            if self.page_number < len(doc):
                page = doc.load_page(self.page_number)
                pix = page.get_pixmap(matrix=fitz.Matrix(self.zoom, self.zoom))
                from PySide6.QtGui import QImage
                img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888)
                self.preview_ready.emit(self.page_number, img.copy())
            doc.close()
            self.finished.emit(True)
        except Exception as e:
            self.error.emit(str(e))
