from services.export.export_manager import ExportPlugin, ExportTask, ExportProfile
from core.logger import logger

class PdfPlugin(ExportPlugin):
    def __init__(self):
        super().__init__()
        self.format_name = "PDF"
        self.supported_extensions = [".pdf"]
        
    def export(self, task: ExportTask, profile: ExportProfile) -> bool:
        logger.info(f"Exporting PDF: {task.target_filename}")
        return True
