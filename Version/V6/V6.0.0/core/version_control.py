import shutil
from pathlib import Path
from datetime import datetime
from core.logger import logger

class VersionControl:
    def __init__(self, backup_dir: str = "backups"):
        self.backup_dir = Path(backup_dir)
        self.backup_dir.mkdir(exist_ok=True)
        
    def snapshot(self, project_path: str):
        """Creates a versioned copy of the current project file."""
        src = Path(project_path)
        if not src.exists():
            return
            
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest = self.backup_dir / f"{src.stem}_{timestamp}{src.suffix}"
        
        try:
            shutil.copy2(src, dest)
            logger.info(f"Version snapshot saved: {dest}")
        except Exception as e:
            logger.error(f"Failed to snapshot {project_path}: {e}")
