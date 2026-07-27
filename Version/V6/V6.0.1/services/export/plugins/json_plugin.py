from services.export.export_manager import ExportPlugin, ExportTask, ExportProfile
from core.logger import logger

class JsonPlugin(ExportPlugin):
    def __init__(self):
        super().__init__()
        self.format_name = "JSON"
        self.supported_extensions = [".json"]
        
    def export(self, task: ExportTask, profile: ExportProfile) -> bool:
        logger.info(f"Exporting JSON: {task.target_filename}")
        return True
