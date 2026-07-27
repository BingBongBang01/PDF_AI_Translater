from PySide6.QtWidgets import QTableWidgetItem, QHeaderView
from ui.widgets.m3_components import MaterialTableWidget
from utils.i18n import tr


class GlossaryTable(MaterialTableWidget):
    def __init__(self, parent=None):
        super().__init__(0, 4, parent)
        self.setHorizontalHeaderLabels([tr("Original"), tr("Translation"), tr("Notes"), tr("Priority")])
        self.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.setSelectionBehavior(MaterialTableWidget.SelectRows)
        self.setEditTriggers(MaterialTableWidget.NoEditTriggers)
        self.load_mock_data()

    def load_mock_data(self):
        mock_data = [
            ("AI", "인공지능", tr("Use full term"), tr("High")),
            ("Machine Learning", "기계 학습", tr("Standard term"), tr("High")),
            ("Deep Learning", "딥러닝", tr("Preferred term"), tr("Medium")),
            ("Model", "모델", tr("Context-dependent"), tr("Low"))
        ]
        self.setRowCount(len(mock_data))
        for row, data in enumerate(mock_data):
            for col, text in enumerate(data):
                self.setItem(row, col, QTableWidgetItem(text))
