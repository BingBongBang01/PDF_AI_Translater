from services.export.export_manager import ExportPlugin, ExportTask, ExportProfile
from core.logger import logger

class DocxPlugin(ExportPlugin):
    def __init__(self):
        super().__init__()
        self.format_name = "DOCX"
        self.supported_extensions = [".docx"]
        
    def export(self, task: ExportTask, profile: ExportProfile) -> bool:
        logger.info(f"Exporting DOCX: {task.target_filename}")
        return True
