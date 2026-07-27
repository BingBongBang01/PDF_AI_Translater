from services.base_service import BaseService
from core.logger import logger
from engine.pdf_engine import PDFEngine
from typing import List, Dict, Any

class PDFService(BaseService):
    """Facade for PDF operations, backed by PDFEngine."""
    def __init__(self):
        self.engine = PDFEngine()

    def load_pdf(self, path: str, password: str = "") -> bool:
        logger.info(f"Loading PDF from {path}")
        return self.engine.open_pdf(path, password)
        
    def close_pdf(self):
        logger.info("Closing PDF")
        self.engine.close_pdf()
        
    def get_bookmarks(self) -> List[Dict[str, Any]]:
        return self.engine.get_bookmarks()
        
    def search(self, text: str) -> List[Any]:
        return self.engine.search(text)
        
    def request_thumbnail(self, page: int):
        self.engine.request_thumbnail(page)
