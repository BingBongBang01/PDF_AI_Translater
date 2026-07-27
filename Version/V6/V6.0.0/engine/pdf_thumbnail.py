import fitz
from PySide6.QtGui import QImage
from PySide6.QtCore import QRunnable, QObject, Signal
from engine.pdf_renderer import PDFRenderer
from core.event_bus import EventBus

class ThumbnailWorkerSignals(QObject):
    finished = Signal(int, QImage)
    error = Signal(int, str)

class PDFThumbnailWorker(QRunnable):
    """Background worker for rendering thumbnails without blocking the GUI."""
    def __init__(self, path: str, page_num: int, zoom: float = 0.2):
        super().__init__()
        self.path = path
        self.page_num = page_num
        self.zoom = zoom
        self.signals = ThumbnailWorkerSignals()
        self.renderer = PDFRenderer()

    def run(self):
        try:
            doc = fitz.open(self.path)
            page = doc.load_page(self.page_num)
            image = self.renderer.render_page(page, self.zoom)
            doc.close()
            self.signals.finished.emit(self.page_num, image)
            EventBus.publish("ThumbnailReady", self.path, self.page_num)
        except Exception as e:
            self.signals.error.emit(self.page_num, str(e))
