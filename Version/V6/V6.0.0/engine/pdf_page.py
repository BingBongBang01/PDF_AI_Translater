import fitz
from typing import Optional

class PDFPage:
    def __init__(self, fitz_page: fitz.Page):
        self.page = fitz_page
        self.number = fitz_page.number
        
    @property
    def rect(self) -> fitz.Rect:
        return self.page.rect
        
    @property
    def rotation(self) -> int:
        return self.page.rotation
        
    def get_text(self, option: str = "text") -> str:
        return self.page.get_text(option)
        
    def get_links(self) -> list:
        return self.page.get_links()
