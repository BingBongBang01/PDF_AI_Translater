from controllers.base_controller import BaseController
from services.history_service import HistoryService


class HistoryController(BaseController):
    """Mediates HistoryPage UI and HistoryService."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.service = HistoryService()

    def get_history(self, limit: int = 100):
        return self.service.get_history(limit)

    def add_history(self, action: str, details: dict):
        self.service.add_history(action, details)

    def remove_history(self, record_id: str):
        self.service.remove_history(record_id)

    def clear_history(self):
        self.service.clear_history()
