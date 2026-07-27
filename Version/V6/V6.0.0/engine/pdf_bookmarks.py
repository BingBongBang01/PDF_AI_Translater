import fitz
from typing import List, Dict, Any

class PDFBookmarks:
    def __init__(self):
        pass

    def extract_bookmarks(self, doc: fitz.Document) -> List[Dict[str, Any]]:
        # PyMuPDF get_toc returns: [level, title, page, ...]
        toc = doc.get_toc()
        bookmarks = []
        for item in toc:
            level = item[0]
            title = item[1]
            page = item[2]
            bookmarks.append({"level": level, "title": title, "page": page})
        return bookmarks
