import fitz
from PySide6.QtGui import QImage
from core.logger import logger

class PDFRenderer:
    def __init__(self):
        pass

    def render_page(self, page: fitz.Page, zoom: float = 1.0) -> QImage:
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        fmt = QImage.Format_RGB888
        image = QImage(pix.samples, pix.width, pix.height, pix.stride, fmt)
        return image.copy() # Detach from pixmap memory
