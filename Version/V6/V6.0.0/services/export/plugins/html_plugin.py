from services.export.export_manager import ExportPlugin, ExportTask, ExportProfile
from core.logger import logger

class HtmlPlugin(ExportPlugin):
    def __init__(self):
        super().__init__()
        self.format_name = "HTML"
        self.supported_extensions = [".html", ".htm"]
        
    def export(self, task: ExportTask, profile: ExportProfile) -> bool:
        logger.info(f"Exporting HTML: {task.target_filename}")
        return True
