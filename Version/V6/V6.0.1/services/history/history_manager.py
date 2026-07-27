import json
import uuid
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any
from core.logger import logger

class HistoryManager:
    def __init__(self, history_file: str = "config/history.json"):
        self.history_file = Path(history_file)
        self.records: List[Dict[str, Any]] = []
        self._load()
        
    def _load(self):
        if self.history_file.exists():
            try:
                self.records = json.loads(self.history_file.read_text(encoding="utf-8"))
            except Exception as e:
                logger.warning(f"Failed to load history: {e}")
                
    def _save(self):
        self.history_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.history_file.write_text(json.dumps(self.records, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            logger.error(f"Failed to save history: {e}")

    def add_record(self, action: str, details: dict):
        record = {
            "id": str(uuid.uuid4()),
            "timestamp": datetime.now().isoformat(),
            "action": action,
            "details": details
        }
        self.records.insert(0, record)
        self._save()
        
    def get_records(self, limit: int = 100) -> List[Dict[str, Any]]:
        return self.records[:limit]

    def remove_record(self, record_id: str):
        self.records = [r for r in self.records if r.get("id") != record_id]
        self._save()

    def clear(self):
        self.records = []
        self._save()
