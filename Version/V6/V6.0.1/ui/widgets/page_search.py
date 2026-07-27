from PySide6.QtWidgets import QWidget, QVBoxLayout, QListWidgetItem
from PySide6.QtCore import Signal
from ui.widgets.m3_components import MaterialListWidget

from ui.widgets.m3_text_field import MaterialTextField


class PageSearch(QWidget):
    page_selected = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)

        self.search_fn = None  # Callable[[str], list[dict]] set by owning page

        self.search_box = MaterialTextField()
        self.search_box.setPlaceholderText("Search in document...")
        self.search_box.returnPressed.connect(self.perform_search)

        self.results_list = MaterialListWidget()
        self.results_list.itemClicked.connect(self._on_item_clicked)

        self.layout.addWidget(self.search_box)
        self.layout.addWidget(self.results_list)

    def set_query_and_search(self, text: str):
        self.search_box.setText(text)
        self.perform_search()

    def perform_search(self):
        query = self.search_box.text()
        self.results_list.clear()
        if not query:
            return

        if not self.search_fn:
            return

        results = self.search_fn(query) or []
        for res in results:
            page = res.get("page", 0)
            count = len(res.get("rects", []))
            item = QListWidgetItem(f"Found '{query}' on page {page + 1} ({count} match{'es' if count != 1 else ''})")
            item.setData(100, page)
            self.results_list.addItem(item)

    def _on_item_clicked(self, item):
        page_idx = item.data(100)
        if page_idx is not None:
            self.page_selected.emit(page_idx)
