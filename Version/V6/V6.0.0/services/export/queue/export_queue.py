from typing import List
from PySide6.QtCore import QThreadPool
from services.export.export_manager import ExportJob
from services.export.queue.export_worker import ExportWorker
from core.logger import logger

class ExportQueue:
    def __init__(self, manager):
        self.manager = manager
        self.thread_pool = QThreadPool.globalInstance()
        self.jobs: List[ExportJob] = []

    def enqueue_job(self, job: ExportJob):
        self.jobs.append(job)
        plugin = self.manager.get_plugin(job.profile.format)
        
        if not plugin:
            logger.error(f"No plugin found for format {job.profile.format}")
            return
            
        for task in job.tasks:
            worker = ExportWorker(task, job.profile, plugin)
            self.thread_pool.start(worker)
