from services.base_service import BaseService
from core.logger import logger
from services.export.export_manager import ExportManager, ExportProfile, ExportTask, ExportJob
from services.export.queue.export_queue import ExportQueue
from typing import List
from services.export.plugins.docx_plugin import DocxPlugin
from services.export.plugins.pdf_plugin import PdfPlugin
from services.export.plugins.txt_plugin import TxtPlugin
from services.export.plugins.html_plugin import HtmlPlugin
from services.export.plugins.md_plugin import MarkdownPlugin
from services.export.plugins.epub_plugin import EpubPlugin
from services.export.plugins.csv_plugin import CsvPlugin
from services.export.plugins.excel_plugin import ExcelPlugin
from services.export.plugins.json_plugin import JsonPlugin

class ExportService(BaseService):
    """Facade for all export operations."""
    def __init__(self):
        self.manager = ExportManager()
        self.queue = ExportQueue(self.manager)
        
        self.manager.register_plugin(DocxPlugin())
        self.manager.register_plugin(PdfPlugin())
        self.manager.register_plugin(TxtPlugin())
        self.manager.register_plugin(HtmlPlugin())
        self.manager.register_plugin(MarkdownPlugin())
        self.manager.register_plugin(EpubPlugin())
        self.manager.register_plugin(CsvPlugin())
        self.manager.register_plugin(ExcelPlugin())
        self.manager.register_plugin(JsonPlugin())

    def start_export(self, profile_dict: dict, tasks_dict: List[dict]) -> str:
        logger.info(f"Starting export job for {len(tasks_dict)} tasks in format {profile_dict.get('format')}")
        
        profile = ExportProfile(
            format=profile_dict["format"],
            destination_folder=profile_dict["destination_folder"],
            filename_template=profile_dict.get("filename_template", "{name}_translated.{ext}"),
            overwrite=profile_dict.get("overwrite", False),
            compress=profile_dict.get("compress", True),
            embed_fonts=profile_dict.get("embed_fonts", True),
            embed_images=profile_dict.get("embed_images", True),
            include_metadata=profile_dict.get("include_metadata", True),
            extra_options=profile_dict.get("extra_options", {})
        )
        
        tasks = []
        for t in tasks_dict:
            task = ExportTask(
                document_id=t["document_id"],
                source_path=t["source_path"],
                target_filename=t["target_filename"]
            )
            tasks.append(task)
            
        job = self.manager.create_job(profile, tasks)
        self.queue.enqueue_job(job)
        return job.job_id
