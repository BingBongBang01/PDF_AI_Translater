from services.export.export_manager import ExportPlugin, ExportTask, ExportProfile
from core.logger import logger

class TxtPlugin(ExportPlugin):
    def __init__(self):
        super().__init__()
        self.format_name = "TXT"
        self.supported_extensions = [".txt"]
        
    def export(self, task: ExportTask, profile: ExportProfile) -> bool:
        logger.info(f"Exporting TXT: {task.target_filename}")
        return True
