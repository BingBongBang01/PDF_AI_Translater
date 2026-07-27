from PySide6.QtWidgets import QTreeWidgetItem
from PySide6.QtCore import Signal
from ui.widgets.m3_components import MaterialTreeWidget


class BookmarkTree(MaterialTreeWidget):
    page_selected = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderHidden(True)
        self.setStyleSheet("""
            MaterialTreeWidget {
                background-color: transparent;
                border: none;
            }
        """)
        self.itemClicked.connect(self._on_item_clicked)

    def load_bookmarks(self, bookmarks):
        """Build the tree from PDFEngine.get_bookmarks() output: [{level, title, page}, ...]."""
        self.clear()
        if not bookmarks:
            return

        stack = [(0, self)]  # (level, parent_item_or_tree)
        for bm in bookmarks:
            level = bm.get("level", 1)
            title = bm.get("title", "")
            page = bm.get("page", 0)

            while stack and stack[-1][0] >= level:
                stack.pop()
            parent = stack[-1][1] if stack else self

            item = QTreeWidgetItem(parent, [title])
            item.setData(0, 100, max(page - 1, 0))  # PyMuPDF TOC pages are 1-indexed
            stack.append((level, item))

        self.expandAll()
        
    def _on_item_clicked(self, item, column):
        page_idx = item.data(0, 100)
        if page_idx is not None:
            self.page_selected.emit(page_idx)
