from core.cache_manager import CacheManager
from core.service_locator import resolve
from typing import Optional
from PySide6.QtGui import QImage

class PDFCache:
    """Manages rendered images and thumbnails, wrapping CacheManager."""
    def __init__(self):
        self.cache = resolve(CacheManager)
        
    def _make_key(self, prefix: str, path: str, page: int, scale: float) -> str:
        return f"{prefix}_{path}_{page}_{scale}"

    def get_thumbnail(self, path: str, page: int, scale: float) -> Optional[QImage]:
        return self.cache.get(self._make_key("thumb", path, page, scale))
        
    def set_thumbnail(self, path: str, page: int, scale: float, image: QImage):
        self.cache.set(self._make_key("thumb", path, page, scale), image)
        
    def get_rendered_page(self, path: str, page: int, scale: float) -> Optional[QImage]:
        return self.cache.get(self._make_key("page", path, page, scale))
        
    def set_rendered_page(self, path: str, page: int, scale: float, image: QImage):
        self.cache.set(self._make_key("page", path, page, scale), image)
