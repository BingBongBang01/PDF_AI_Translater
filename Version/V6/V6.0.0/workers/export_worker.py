from PySide6.QtCore import Signal
from workers.base_worker import BaseWorker
from services.export.export_manager import ExportTask, ExportProfile, ExportManager

class ExportWorker(BaseWorker):
    """Executes export tasks in the background using registered plugins."""
    task_progress = Signal(str, float) # task_id, progress
    task_completed = Signal(str, bool) # task_id, success
    
    def __init__(self, task: ExportTask, profile: ExportProfile, parent=None):
        super().__init__(parent)
        self.task = task
        self.profile = profile
        
    def run(self):
        try:
            manager = ExportManager()
            plugin = manager.get_plugin(self.profile.format)
            if not plugin:
                raise ValueError(f"No plugin registered for format: {self.profile.format}")
                
            # Simulate work
            self.task_progress.emit(self.task.document_id, 0.5)
            success = plugin.export(self.task, self.profile)
            
            self.task_completed.emit(self.task.document_id, success)
            self.finished.emit(True)
        except Exception as e:
            self.error.emit(str(e))

class ValidationWorker(BaseWorker):
    """Checks for missing fonts, images, or broken tables before export."""
    validation_done = Signal(str, list) # task_id, warnings
    
    def __init__(self, task: ExportTask, profile: ExportProfile, parent=None):
        super().__init__(parent)
        self.task = task
        self.profile = profile
        
    def run(self):
        try:
            manager = ExportManager()
            plugin = manager.get_plugin(self.profile.format)
            warnings = []
            if plugin:
                warnings = plugin.validate(self.task)
            self.validation_done.emit(self.task.document_id, warnings)
            self.finished.emit(True)
        except Exception as e:
            self.error.emit(str(e))

class PreviewWorker(BaseWorker):
    """Generates an HTML/RichText preview of the final exported format."""
    preview_ready = Signal(str)
    
    def __init__(self, document_id, parent=None):
        super().__init__(parent)
        self.document_id = document_id
        
    def run(self):
        # Simulate preview generation
        html_preview = f"<h1>Preview for {self.document_id}</h1><p>Formatting applied.</p>"
        self.preview_ready.emit(html_preview)
        self.finished.emit(True)

class CompressionWorker(BaseWorker):
    """Handles zip/compression of large outputs post-export."""
    compression_done = Signal(str) # output_path
    
    def __init__(self, file_path, parent=None):
        super().__init__(parent)
        self.file_path = file_path
        
    def run(self):
        # Simulate compression
        import time
        time.sleep(0.5)
        self.compression_done.emit(self.file_path + ".zip")
        self.finished.emit(True)
