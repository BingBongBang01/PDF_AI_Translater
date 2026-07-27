from PySide6.QtWidgets import QVBoxLayout
from PySide6.QtCore import Qt, Signal
from ui.widgets.m3_components import MaterialLabel, MaterialFrame
from utils.i18n import tr


class FileDropArea(MaterialFrame):
    files_dropped = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setStyleSheet("""
            MaterialFrame {
                border: 2px dashed var(--md-sys-color-outline);
                border-radius: 12px;
                background-color: transparent;
            }
            MaterialFrame.drag-hover {
                border: 2px solid var(--md-sys-color-primary);
                background-color: var(--md-sys-color-primary-container);
            }
        """)
        
        self.layout = QVBoxLayout(self)
        self.lbl_text = MaterialLabel(tr("Drag & Drop PDF, Images, or Folders here"))
        self.lbl_text.setAlignment(Qt.AlignCenter)
        self.lbl_text.setStyleSheet("color: var(--md-sys-color-on-surface-variant); font-size: 16px; border: none;")
        self.layout.addWidget(self.lbl_text)
        
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.setProperty("class", "drag-hover")
            self.style().unpolish(self)
            self.style().polish(self)
            
    def dragLeaveEvent(self, event):
        self.setProperty("class", "")
        self.style().unpolish(self)
        self.style().polish(self)
        
    def dropEvent(self, event):
        self.setProperty("class", "")
        self.style().unpolish(self)
        self.style().polish(self)
        
        urls = event.mimeData().urls()
        files = [u.toLocalFile() for u in urls if u.isLocalFile()]
        if files:
            self.lbl_text.setText(f"{tr('Dropped')}: {files[0]} {'(+' + str(len(files)-1) + ' ' + tr('more') + ')' if len(files)>1 else ''}")
            self.files_dropped.emit(files)
