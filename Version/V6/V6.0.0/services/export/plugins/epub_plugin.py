from services.export.export_manager import ExportPlugin, ExportTask, ExportProfile
from core.logger import logger

class EpubPlugin(ExportPlugin):
    def __init__(self):
        super().__init__()
        self.format_name = "EPUB"
        self.supported_extensions = [".epub"]
        
    def export(self, task: ExportTask, profile: ExportProfile) -> bool:
        logger.info(f"Exporting EPUB: {task.target_filename}")
        return True
