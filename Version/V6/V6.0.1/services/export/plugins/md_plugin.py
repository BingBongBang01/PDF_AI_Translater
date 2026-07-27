from services.export.export_manager import ExportPlugin, ExportTask, ExportProfile
from core.logger import logger

class MarkdownPlugin(ExportPlugin):
    def __init__(self):
        super().__init__()
        self.format_name = "Markdown"
        self.supported_extensions = [".md"]
        
    def export(self, task: ExportTask, profile: ExportProfile) -> bool:
        logger.info(f"Exporting Markdown: {task.target_filename}")
        return True
