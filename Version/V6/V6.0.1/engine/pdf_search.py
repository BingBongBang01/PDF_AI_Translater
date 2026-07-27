import fitz
import re
from typing import List, Tuple

class PDFSearch:
    def __init__(self):
        pass

    def search_text(self, page: fitz.Page, text: str, regex: bool = False, case_sensitive: bool = False, whole_word: bool = False) -> List[fitz.Rect]:
        if not regex and not whole_word:
            # Basic PyMuPDF search
            return page.search_for(text)
            
        # Advanced search stub
        return page.search_for(text)
