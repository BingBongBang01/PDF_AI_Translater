from services.export.export_manager import ExportPlugin, ExportTask, ExportProfile
from core.logger import logger

class CsvPlugin(ExportPlugin):
    def __init__(self):
        super().__init__()
        self.format_name = "CSV"
        self.supported_extensions = [".csv"]
        
    def export(self, task: ExportTask, profile: ExportProfile) -> bool:
        logger.info(f"Exporting CSV: {task.target_filename}")
        return True
