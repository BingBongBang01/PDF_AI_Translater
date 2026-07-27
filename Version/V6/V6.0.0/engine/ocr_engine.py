from typing import Dict, List, Any, Optional
from PySide6.QtCore import QThreadPool
from engine.ocr_queue import OCRQueue
from engine.ocr_plugins import BaseOCRPlugin, TesseractPlugin, EasyOCRPlugin, PaddleOCRPlugin
from engine.ocr_worker import OCRWorker
from core.logger import logger
from core.event_bus import EventBus

class OCREngine:
    def __init__(self):
        self.queue = OCRQueue()
        self.thread_pool = QThreadPool.globalInstance()
        self.plugins: Dict[str, BaseOCRPlugin] = {
            "tesseract": TesseractPlugin(),
            "easyocr": EasyOCRPlugin(),
            "paddleocr": PaddleOCRPlugin()
        }
        self.current_plugin: str = "tesseract"
        
    def set_engine(self, engine_name: str, lang: str = "eng"):
        if engine_name in self.plugins:
            self.current_plugin = engine_name
            self.plugins[engine_name].load_model(lang)
            logger.info(f"Set OCR engine to {engine_name}")
        else:
            logger.error(f"OCR Engine {engine_name} not found.")
            
    def enqueue_image(self, image_path: str, lang: str = "eng", page_num: int = 0) -> str:
        job_id = self.queue.add_job(image_path, lang, page_num)
        self._process_next()
        return job_id
        
    def _process_next(self):
        job = self.queue.get_next_job()
        if not job:
            return
            
        plugin = self.plugins[self.current_plugin]
        worker = OCRWorker(job.job_id, job.image_path, job.lang, plugin)
        
        # Connect signals
        worker.signals.finished.connect(lambda jid, res: self._on_job_finished(jid, res))
        worker.signals.error.connect(lambda jid, err: self._on_job_error(jid, err))
        
        self.thread_pool.start(worker)
        
    def _on_job_finished(self, job_id: str, results: list):
        self.queue.update_job(job_id, "FINISHED", result=results)
        self._process_next()
        
    def _on_job_error(self, job_id: str, error: str):
        self.queue.update_job(job_id, "FAILED", error=error)
        self._process_next()
