from PySide6.QtWidgets import QListWidgetItem
from PySide6.QtCore import Qt, QSize, Signal
from PySide6.QtGui import QIcon, QPixmap
from ui.widgets.m3_components import MaterialListWidget


class ThumbnailList(MaterialListWidget):
    """Virtualized thumbnail list for displaying PDF pages."""
    page_selected = Signal(int)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setViewMode(MaterialListWidget.IconMode)
        self.setIconSize(QSize(120, 160))
        self.setResizeMode(MaterialListWidget.Adjust)
        self.setSpacing(10)
        self.setMovement(MaterialListWidget.Static)
        self.setSelectionMode(MaterialListWidget.ExtendedSelection)
        self.setStyleSheet("""
            MaterialListWidget {
                background-color: transparent;
                border: none;
            }
            MaterialListWidget::item {
                border-radius: 8px;
            }
            MaterialListWidget::item:selected {
                background-color: var(--md-sys-color-primary-container);
                border: 2px solid var(--md-sys-color-primary);
            }
        """)
        
        self.itemClicked.connect(self._on_click)
        
    def init_pages(self, total_pages):
        self.clear()
        for i in range(total_pages):
            item = QListWidgetItem()
            item.setText(f"{i+1}")
            item.setTextAlignment(Qt.AlignCenter)
            # Size hint ensures the item holds space even before the image loads
            item.setSizeHint(QSize(140, 190))
            # Placeholder icon
            item.setIcon(QIcon())
            self.addItem(item)
            
    def set_thumbnail(self, page_number, image):
        if page_number < self.count():
            item = self.item(page_number)
            pixmap = QPixmap.fromImage(image)
            item.setIcon(QIcon(pixmap))
            
    def _on_click(self, item):
        row = self.row(item)
        self.page_selected.emit(row)
