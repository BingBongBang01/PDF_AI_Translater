import fitz
from typing import Optional, List, Dict, Any
from core.logger import logger
from core.exceptions import AppError

class PDFDocumentError(AppError):
    pass

class PDFDocument:
    def __init__(self):
        self.doc: Optional[fitz.Document] = None
        self.file_path: Optional[str] = None
        
    def open(self, path: str, password: str = "") -> bool:
        try:
            self.doc = fitz.open(path)
            if self.doc.needs_pass:
                if not self.doc.authenticate(password):
                    raise PDFDocumentError("Password required or incorrect.")
            self.file_path = path
            logger.info(f"Opened PDF: {path} with {self.page_count} pages.")
            return True
        except Exception as e:
            logger.error(f"Failed to open PDF {path}: {e}")
            raise PDFDocumentError(f"Cannot open PDF: {e}")
            
    def close(self):
        if self.doc:
            self.doc.close()
            self.doc = None
            self.file_path = None
            logger.info("Closed PDF.")
            
    @property
    def page_count(self) -> int:
        return self.doc.page_count if self.doc else 0
        
    @property
    def metadata(self) -> Dict[str, Any]:
        return self.doc.metadata if self.doc else {}
        
    def get_page(self, page_num: int) -> Optional[fitz.Page]:
        if self.doc and 0 <= page_num < self.page_count:
            return self.doc.load_page(page_num)
        return None

    def is_encrypted(self) -> bool:
        return self.doc.is_encrypted if self.doc else False
