import json
import threading
import time
from pathlib import Path
from core.logger import logger
from core.event_bus import EventBus
from core.session_manager import SessionManager

class WorkspaceManager:
    def __init__(self, session_manager: SessionManager):
        self.session = session_manager
        self.auto_save_interval = 300
        self.auto_save_timer = None
        self._running = False
        
    def start_auto_save(self):
        self._running = True
        self._auto_save_loop()
        
    def stop_auto_save(self):
        self._running = False
        if self.auto_save_timer:
            self.auto_save_timer.cancel()
            
    def _auto_save_loop(self):
        if not self._running:
            return
            
        logger.info("Auto-saving workspace state...")
        self.save_workspace()
        EventBus.publish("WorkspaceAutoSaved")
        
        self.auto_save_timer = threading.Timer(self.auto_save_interval, self._auto_save_loop)
        self.auto_save_timer.daemon = True
        self.auto_save_timer.start()

    def load_workspace(self, path: str):
        logger.info(f"Loading workspace from {path}")
        p = Path(path)
        if p.exists():
            data = json.loads(p.read_text(encoding="utf-8"))
            self.session.state.update(data)
            self.session.save_session()
            EventBus.publish("WorkspaceLoaded", path)
            
    def save_workspace(self, path: str = None):
        target = Path(path) if path else Path("config/recovery.json")
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            target.write_text(json.dumps(self.session.state, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            logger.error(f"Failed to save workspace: {e}")
