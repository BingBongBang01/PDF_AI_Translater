import fitz
from typing import Optional

class PDFSelection:
    def __init__(self):
        pass

    def extract_text_from_rect(self, page: fitz.Page, rect: fitz.Rect) -> str:
        return page.get_textbox(rect)
