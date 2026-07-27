from typing import List, Dict, Any, Optional
from PySide6.QtGui import QImage
from PySide6.QtCore import QThreadPool
from engine.pdf_document import PDFDocument
from engine.pdf_renderer import PDFRenderer
from engine.pdf_search import PDFSearch
from engine.pdf_bookmarks import PDFBookmarks
from engine.pdf_selection import PDFSelection
from engine.pdf_cache import PDFCache
from engine.pdf_thumbnail import PDFThumbnailWorker
from core.event_bus import EventBus
from core.logger import logger

class PDFEngine:
    """Orchestrates all PDF operations."""
    def __init__(self):
        self.doc = PDFDocument()
        self.renderer = PDFRenderer()
        self.searcher = PDFSearch()
        self.bookmarks = PDFBookmarks()
        self.selection = PDFSelection()
        self.cache = PDFCache()
        self.thread_pool = QThreadPool.globalInstance()

    def open_pdf(self, path: str, password: str = "") -> bool:
        success = self.doc.open(path, password)
        if success:
            EventBus.publish("PDFOpened", path)
        return success

    def close_pdf(self):
        path = self.doc.file_path
        self.doc.close()
        if path:
            EventBus.publish("PDFClosed", path)

    def request_thumbnail(self, page_num: int, zoom: float = 0.2):
        path = self.doc.file_path
        if not path:
            return
            
        cached = self.cache.get_thumbnail(path, page_num, zoom)
        if cached:
            EventBus.publish("ThumbnailReady", path, page_num)
            return

        worker = PDFThumbnailWorker(path, page_num, zoom)
        # Real impl would cache it upon finish via signals
        self.thread_pool.start(worker)
        
    def get_bookmarks(self) -> List[Dict[str, Any]]:
        if not self.doc.doc:
            return []
        bms = self.bookmarks.extract_bookmarks(self.doc.doc)
        EventBus.publish("BookmarksLoaded", len(bms))
        return bms
        
    def search(self, text: str, regex: bool = False) -> List[Any]:
        if not self.doc.doc:
            return []
        results = []
        for i in range(self.doc.page_count):
            page = self.doc.get_page(i)
            if page:
                res = self.searcher.search_text(page, text, regex)
                if res:
                    results.append({"page": i, "rects": res})
        EventBus.publish("SearchCompleted", text, len(results))
        return results
