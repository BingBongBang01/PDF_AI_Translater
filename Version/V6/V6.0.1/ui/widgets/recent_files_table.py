from PySide6.QtWidgets import QTableWidgetItem, QHeaderView
from ui.widgets.m3_components import MaterialTableWidget
from utils.i18n import tr


class RecentFilesTable(MaterialTableWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setColumnCount(5)
        self.setHorizontalHeaderLabels([tr("File Name"), tr("Date"), tr("Pages"), tr("Language"), tr("Status")])
        self.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.verticalHeader().setVisible(False)
        self.setSelectionBehavior(MaterialTableWidget.SelectRows)
        self.setShowGrid(False)
        self.setEditTriggers(MaterialTableWidget.NoEditTriggers)

    def load_mock_data(self):
        mock_files = [
            ("comic_vol1.pdf", "2026-07-27", "200", "JP -> KR", tr("Completed")),
            ("document_v2.pdf", "2026-07-26", "15", "EN -> KR", tr("Processing...")),
            ("invoice_scanned.png", "2026-07-25", "1", "AUTO -> EN", tr("Failed"))
        ]
        self.setRowCount(len(mock_files))
        for row, data in enumerate(mock_files):
            for col, text in enumerate(data):
                self.setItem(row, col, QTableWidgetItem(text))
