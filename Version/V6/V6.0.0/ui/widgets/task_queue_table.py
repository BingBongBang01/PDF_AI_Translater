from PySide6.QtWidgets import QTableWidgetItem, QHeaderView
from ui.widgets.m3_components import MaterialTableWidget


class TaskQueueTable(MaterialTableWidget):
    def __init__(self, headers, parent=None):
        super().__init__(0, len(headers), parent)
        self.setHorizontalHeaderLabels(headers)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.setSelectionBehavior(MaterialTableWidget.SelectRows)
        self.setEditTriggers(MaterialTableWidget.NoEditTriggers)

    def load_data(self, mock_data):
        self.setRowCount(len(mock_data))
        for row, data in enumerate(mock_data):
            for col, text in enumerate(data):
                self.setItem(row, col, QTableWidgetItem(str(text)))
