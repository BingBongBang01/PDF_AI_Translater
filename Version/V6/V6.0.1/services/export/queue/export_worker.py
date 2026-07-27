from PySide6.QtCore import QRunnable, QObject, Signal
from services.export.export_manager import ExportTask, ExportProfile
from core.event_bus import EventBus
from core.logger import logger
from services.export.modifiers.formatter import Formatter
from services.export.modifiers.metadata_injector import MetadataInjector
from services.export.modifiers.watermarker import Watermarker
from services.export.modifiers.encryptor import Encryptor

class ExportWorkerSignals(QObject):
    finished = Signal(str, bool)
    error = Signal(str, str)

class ExportWorker(QRunnable):
    def __init__(self, task: ExportTask, profile: ExportProfile, plugin):
        super().__init__()
        self.task = task
        self.profile = profile
        self.plugin = plugin
        self.signals = ExportWorkerSignals()

    def run(self):
        try:
            EventBus.publish("ExportStarted", self.task.document_id)
            
            success = self.plugin.export(self.task, self.profile)
            if not success:
                raise Exception("Plugin export failed")
                
            filepath = self.task.target_filename
            Formatter.apply_formatting(filepath, self.profile.extra_options)
            
            if self.profile.include_metadata:
                MetadataInjector.inject(filepath, self.profile.extra_options)
                
            if self.profile.extra_options.get("watermark"):
                Watermarker.apply(filepath, self.profile.extra_options["watermark"])
                
            if self.profile.extra_options.get("encryption"):
                Encryptor.encrypt(filepath, self.profile.extra_options["encryption"])

            self.task.status = "Completed"
            self.task.progress = 100.0
            self.signals.finished.emit(self.task.document_id, True)
            EventBus.publish("ExportFinished", self.task.document_id)
        except Exception as e:
            logger.error(f"Export failed for {self.task.document_id}: {e}")
            self.task.status = "Failed"
            self.signals.error.emit(self.task.document_id, str(e))
            EventBus.publish("ExportFailed", self.task.document_id, str(e))
