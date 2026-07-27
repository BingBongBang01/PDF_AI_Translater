from controllers.base_controller import BaseController
from services.pdf_service import PDFService


class PDFController(BaseController):
    """Mediates PDFPage UI actions and PDFService (bookmarks/search)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.service = PDFService()

    def open(self, path: str) -> bool:
        return self.service.load_pdf(path)

    def close(self):
        self.service.close_pdf()

    def bookmarks(self):
        return self.service.get_bookmarks()

    def search(self, text: str):
        return self.service.search(text)
