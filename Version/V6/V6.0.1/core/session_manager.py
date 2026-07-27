from typing import Any, Dict, List
from core.event_bus import EventBus
import json
from pathlib import Path
from core.logger import logger

class SessionManager:
    """Maintains volatile runtime state and auto-recovery sessions."""
    def __init__(self, session_file: str = "config/session.json"):
        self.session_file = Path(session_file)
        self.state: Dict[str, Any] = {
            "current_project": None,
            "opened_documents": [],
            "selected_page": 0,
            "zoom": 100,
            "window_state": None,
            "recent_files": []
        }
        self._load_session()

    def _load_session(self):
        if self.session_file.exists():
            try:
                data = json.loads(self.session_file.read_text(encoding="utf-8"))
                self.state.update(data)
            except Exception as e:
                logger.warning(f"Could not load session, starting fresh: {e}")

    def save_session(self):
        self.session_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.session_file.write_text(json.dumps(self.state, ensure_ascii=False, indent=4), encoding="utf-8")
        except Exception as e:
            logger.error(f"Failed to save session: {e}")

    def get(self, key: str, default: Any = None) -> Any:
        return self.state.get(key, default)

    def set(self, key: str, value: Any):
        self.state[key] = value
        self.save_session()

    def add_recent_file(self, filepath: str):
        recent = self.state.get("recent_files", [])
        if filepath in recent:
            recent.remove(filepath)
        recent.insert(0, filepath)
        self.state["recent_files"] = recent[:10]  # Keep last 10
        self.save_session()
