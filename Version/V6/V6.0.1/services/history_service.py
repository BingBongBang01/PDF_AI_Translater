from services.base_service import BaseService
from core.logger import logger
from services.history.history_manager import HistoryManager

class HistoryService(BaseService):
    """Facade for History operations."""
    def __init__(self):
        self.manager = HistoryManager()
        
    def get_history(self, limit: int = 100):
        logger.info("Fetching history...")
        return self.manager.get_records(limit)
        
    def add_history(self, action: str, details: dict):
        self.manager.add_record(action, details)

    def remove_history(self, record_id: str):
        self.manager.remove_record(record_id)

    def clear_history(self):
        self.manager.clear()
