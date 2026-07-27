from typing import Dict
from PySide6.QtCore import QThread, QObject
from core.logger import logger
from core.exceptions import TaskError

class WorkerManager:
    """Manages QThread lifecycles, preventing duplicates and ensuring safe shutdown."""
    def __init__(self):
        self._workers: Dict[str, QThread] = {}

    def register_worker(self, task_id: str, thread: QThread):
        if task_id in self._workers:
            raise TaskError(f"Worker for task {task_id} is already running.")
        self._workers[task_id] = thread
        
        # Auto-unregister on finish
        thread.finished.connect(lambda: self._unregister_worker(task_id))
        logger.debug(f"Worker registered for task {task_id}")

    def start_worker(self, task_id: str):
        if task_id in self._workers:
            self._workers[task_id].start()
            logger.info(f"Started worker for task {task_id}")

    def _unregister_worker(self, task_id: str):
        if task_id in self._workers:
            del self._workers[task_id]
            logger.debug(f"Worker unregistered for task {task_id}")

    def cancel_worker(self, task_id: str):
        if task_id in self._workers:
            thread = self._workers[task_id]
            if hasattr(thread, 'cancel'):
                thread.cancel()
            else:
                thread.requestInterruption()
            logger.info(f"Cancel requested for worker {task_id}")

    def terminate_worker(self, task_id: str):
        if task_id in self._workers:
            thread = self._workers[task_id]
            thread.terminate()
            thread.wait()
            self._unregister_worker(task_id)
            logger.warning(f"Terminated worker {task_id}")

    def shutdown_all(self):
        for task_id in list(self._workers.keys()):
            self.cancel_worker(task_id)
        
        for thread in self._workers.values():
            thread.wait(1000)
            if thread.isRunning():
                thread.terminate()
                thread.wait()
        self._workers.clear()
        logger.info("All workers shut down.")
