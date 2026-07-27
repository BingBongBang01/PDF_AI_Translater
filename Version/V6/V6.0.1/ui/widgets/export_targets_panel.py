from PySide6.QtWidgets import QWidget, QVBoxLayout
from ui.widgets.m3_components import MaterialLabel, MaterialListWidget
from utils.i18n import tr


class ExportTargetsPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(8, 8, 8, 8)

        lbl = MaterialLabel(f"<b>{tr('Export Formats')}</b>")
        self.layout.addWidget(lbl)

        self.target_list = MaterialListWidget()
        self.target_list.addItems([
            tr("PDF Document") + " (.pdf)",
            tr("Word Document") + " (.docx)",
            tr("Plain Text") + " (.txt)",
            tr("Markdown") + " (.md)",
            tr("HTML File") + " (.html)",
            tr("EPUB eBook") + " (.epub)",
            tr("JSON Data") + " (.json)",
            tr("CSV Spreadsheet") + " (.csv)",
            tr("Excel Spreadsheet") + " (.xlsx)"
        ])
        self.target_list.setCurrentRow(0)
        self.layout.addWidget(self.target_list)
