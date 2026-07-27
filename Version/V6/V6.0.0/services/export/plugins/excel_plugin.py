from services.export.export_manager import ExportPlugin, ExportTask, ExportProfile
from core.logger import logger

class ExcelPlugin(ExportPlugin):
    def __init__(self):
        super().__init__()
        self.format_name = "Excel"
        self.supported_extensions = [".xlsx"]
        
    def export(self, task: ExportTask, profile: ExportProfile) -> bool:
        logger.info(f"Exporting Excel: {task.target_filename}")
        return True
