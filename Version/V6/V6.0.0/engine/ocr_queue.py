from typing import List, Dict, Any, Optional
import uuid

class OCRJob:
    def __init__(self, image_path: str, lang: str, page_num: int = 0):
        self.job_id = str(uuid.uuid4())
        self.image_path = image_path
        self.lang = lang
        self.page_num = page_num
        self.status = "QUEUED"
        self.progress = 0
        self.result = None
        self.error = None

class OCRQueue:
    def __init__(self):
        self.jobs: Dict[str, OCRJob] = {}
        self.pending_jobs: List[str] = []
        
    def add_job(self, image_path: str, lang: str, page_num: int = 0) -> str:
        job = OCRJob(image_path, lang, page_num)
        self.jobs[job.job_id] = job
        self.pending_jobs.append(job.job_id)
        return job.job_id
        
    def get_next_job(self) -> Optional[OCRJob]:
        if not self.pending_jobs:
            return None
        job_id = self.pending_jobs.pop(0)
        job = self.jobs[job_id]
        job.status = "RUNNING"
        return job
        
    def update_job(self, job_id: str, status: str, result: Any = None, error: str = None):
        if job_id in self.jobs:
            job = self.jobs[job_id]
            job.status = status
            if result:
                job.result = result
            if error:
                job.error = error
