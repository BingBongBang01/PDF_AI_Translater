from PySide6.QtWidgets import QTableWidgetItem, QHeaderView
from ui.widgets.m3_components import MaterialTableWidget


class TranslationMemoryTable(MaterialTableWidget):
    def __init__(self, parent=None):
        super().__init__(0, 5, parent)
        self.setHorizontalHeaderLabels(["Similarity", "Source", "Target", "Date", "Provider"])
        self.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.setSelectionBehavior(MaterialTableWidget.SelectRows)
        self.setEditTriggers(MaterialTableWidget.NoEditTriggers)
        self.load_mock_data()

    def load_mock_data(self):
        mock_data = [
            ("98%", "The quick brown fox", "빠른 갈색 여우", "2026-07-27", "Google Gemini"),
            ("100%", "Hello world", "안녕 세상", "2026-07-26", "OpenAI GPT-4"),
            ("85%", "Jumped over the lazy dog", "게으른 개를 뛰어 넘었다", "2026-07-25", "Claude 3"),
        ]
        self.setRowCount(len(mock_data))
        for row, data in enumerate(mock_data):
            for col, text in enumerate(data):
                self.setItem(row, col, QTableWidgetItem(text))
