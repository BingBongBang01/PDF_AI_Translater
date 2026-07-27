from PySide6.QtWidgets import QTableWidgetItem, QHeaderView
from ui.widgets.m3_components import MaterialTableWidget


class GlossaryTable(MaterialTableWidget):
    def __init__(self, parent=None):
        super().__init__(0, 4, parent)
        self.setHorizontalHeaderLabels(["Original", "Translation", "Notes", "Priority"])
        self.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.setSelectionBehavior(MaterialTableWidget.SelectRows)
        self.setEditTriggers(MaterialTableWidget.NoEditTriggers)
        self.load_mock_data()

    def load_mock_data(self):
        mock_data = [
            ("AI", "인공지능", "Use full term", "High"),
            ("Machine Learning", "기계 학습", "Standard term", "High"),
            ("Deep Learning", "딥러닝", "Preferred term", "Medium"),
            ("Model", "모델", "Context-dependent", "Low")
        ]
        self.setRowCount(len(mock_data))
        for row, data in enumerate(mock_data):
            for col, text in enumerate(data):
                self.setItem(row, col, QTableWidgetItem(text))
