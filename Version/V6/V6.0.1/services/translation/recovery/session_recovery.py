import json
import os
from typing import Dict, Any

class SessionRecovery:
    """Manages crash recovery by storing partial session state to disk."""
    
    def __init__(self, session_id: str, storage_dir: str = "sessions"):
        self.session_id = session_id
        self.file_path = os.path.join(storage_dir, f"{session_id}.json")
        os.makedirs(storage_dir, exist_ok=True)
        self.state: Dict[str, Any] = {"completed_chunks": [], "failed_chunks": []}
        
    def load(self) -> bool:
        if os.path.exists(self.file_path):
            try:
                with open(self.file_path, "r", encoding="utf-8") as f:
                    self.state = json.load(f)
                return True
            except Exception:
                pass
        return False
        
    def save(self) -> None:
        with open(self.file_path, "w", encoding="utf-8") as f:
            json.dump(self.state, f)
            
    def mark_completed(self, chunk_id: str) -> None:
        if chunk_id not in self.state["completed_chunks"]:
            self.state["completed_chunks"].append(chunk_id)
            if chunk_id in self.state["failed_chunks"]:
                self.state["failed_chunks"].remove(chunk_id)
        self.save()
