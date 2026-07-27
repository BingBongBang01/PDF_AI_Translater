import os
from PySide6.QtCore import QObject, Signal, QThreadPool
from controllers.base_controller import BaseController
from services.export_service import ExportService
from services.export.export_manager import ExportProfile, ExportTask
from services.export.queue.export_worker import ExportWorker

FORMAT_MAP = {
    "PDF Document (.pdf)": ("PDF", ".pdf"),
    "Word Document (.docx)": ("DOCX", ".docx"),
    "Plain Text (.txt)": ("TXT", ".txt"),
    "Markdown (.md)": ("MARKDOWN", ".md"),
    "HTML File (.html)": ("HTML", ".html"),
    "EPUB eBook (.epub)": ("EPUB", ".epub"),
    "JSON Data (.json)": ("JSON", ".json"),
    "CSV Spreadsheet (.csv)": ("CSV", ".csv"),
    "Excel Spreadsheet (.xlsx)": ("EXCEL", ".xlsx"),
}


class ExportController(BaseController):
    """Mediates ExportPage UI and ExportService, one task at a time."""
    task_finished = Signal(str, bool, str)  # document_id, success, message

    def __init__(self, parent=None):
        super().__init__(parent)
        self.service = ExportService()
        self.thread_pool = QThreadPool.globalInstance()
        self._active_signals = []

    def export_file(self, source_path: str, target_label: str, destination_folder: str, options: dict):
        format_name, ext = FORMAT_MAP.get(target_label, ("PDF", ".pdf"))

        profile = ExportProfile(
            format=format_name,
            destination_folder=destination_folder,
            filename_template=options.get("filename_template", "{name}_translated{ext}"),
            overwrite=options.get("overwrite", False),
            compress=options.get("compress", True),
            include_metadata=options.get("include_metadata", True),
            extra_options=options.get("extra_options", {}),
        )

        base_name = os.path.splitext(os.path.basename(source_path))[0]
        target_filename = os.path.join(destination_folder, f"{base_name}_translated{ext}")

        task = ExportTask(document_id=base_name, source_path=source_path, target_filename=target_filename)

        plugin = self.service.manager.get_plugin(format_name)
        if not plugin:
            self.task_finished.emit(task.document_id, False, f"No export plugin registered for {format_name}")
            return task

        worker = ExportWorker(task, profile, plugin)
        worker.signals.finished.connect(lambda doc_id, ok: self.task_finished.emit(doc_id, ok, target_filename))
        worker.signals.error.connect(lambda doc_id, err: self.task_finished.emit(doc_id, False, err))
        self._active_signals.append(worker.signals)  # keep alive until thread pool finishes
        self.thread_pool.start(worker)
        return task
