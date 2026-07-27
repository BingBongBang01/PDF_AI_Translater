from PySide6.QtWidgets import QWidget, QVBoxLayout
from ui.widgets.m3_components import MaterialLabel, MaterialListWidget


class ExportTargetsPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(8, 8, 8, 8)
        
        lbl = MaterialLabel("<b>Export Formats</b>")
        self.layout.addWidget(lbl)
        
        self.target_list = MaterialListWidget()
        self.target_list.addItems([
            "PDF Document (.pdf)",
            "Word Document (.docx)",
            "Plain Text (.txt)",
            "Markdown (.md)",
            "HTML File (.html)",
            "EPUB eBook (.epub)",
            "JSON Data (.json)",
            "CSV Spreadsheet (.csv)",
            "Excel Spreadsheet (.xlsx)"
        ])
        self.target_list.setCurrentRow(0)
        self.layout.addWidget(self.target_list)
