from enum import Enum, auto
from typing import Dict, List, Any, Optional
import uuid
from core.event_bus import EventBus
from core.logger import logger
from core.exceptions import TaskError

class TaskState(Enum):
    QUEUED = auto()
    PENDING = auto()
    RUNNING = auto()
    PAUSED = auto()
    CANCELLED = auto()
    FINISHED = auto()
    FAILED = auto()
    RETRYING = auto()

class Task:
    def __init__(self, name: str, priority: int = 0, dependencies: List[str] = None):
        self.task_id = str(uuid.uuid4())
        self.name = name
        self.state = TaskState.QUEUED
        self.priority = priority
        self.dependencies = dependencies or []
        self.progress = 0
        self.metadata: Dict[str, Any] = {}
        self.error: Optional[str] = None
        self.retries = 0
        self.max_retries = 3

class TaskManager:
    """Manages task lifecycle, dependencies, and queueing."""
    def __init__(self):
        self.tasks: Dict[str, Task] = {}

    def submit_task(self, task: Task) -> str:
        self.tasks[task.task_id] = task
        logger.info(f"Task {task.task_id} ({task.name}) submitted.")
        EventBus.publish("TaskStarted", task.task_id)
        self._check_dependencies(task)
        return task.task_id

    def _check_dependencies(self, task: Task):
        if not task.dependencies:
            self._set_state(task.task_id, TaskState.PENDING)
            
    def _set_state(self, task_id: str, state: TaskState):
        if task_id in self.tasks:
            task = self.tasks[task_id]
            task.state = state
            logger.debug(f"Task {task_id} transitioned to {state.name}")
            
            if state == TaskState.FINISHED:
                EventBus.publish("TaskFinished", task_id)
            elif state == TaskState.CANCELLED:
                EventBus.publish("TaskCancelled", task_id)
            elif state == TaskState.FAILED:
                EventBus.publish("TaskFailed", task_id, task.error or "Unknown Error")
            elif state == TaskState.PAUSED:
                EventBus.publish("TaskPaused", task_id)

    def update_progress(self, task_id: str, progress: int, status_text: str = ""):
        if task_id in self.tasks:
            self.tasks[task_id].progress = progress
            if status_text:
                self.tasks[task_id].metadata["status"] = status_text
            EventBus.publish("TaskUpdated", task_id, status_text)
            EventBus.publish("ProgressChanged", task_id, progress)

    def pause_task(self, task_id: str):
        self._set_state(task_id, TaskState.PAUSED)

    def resume_task(self, task_id: str):
        self._set_state(task_id, TaskState.RUNNING)

    def cancel_task(self, task_id: str):
        self._set_state(task_id, TaskState.CANCELLED)

    def fail_task(self, task_id: str, error: str):
        task = self.tasks.get(task_id)
        if task:
            if task.retries < task.max_retries:
                task.retries += 1
                task.error = error
                self._set_state(task_id, TaskState.RETRYING)
            else:
                task.error = error
                self._set_state(task_id, TaskState.FAILED)

    def finish_task(self, task_id: str):
        self._set_state(task_id, TaskState.FINISHED)
        self._resolve_dependencies(task_id)
        
    def _resolve_dependencies(self, finished_task_id: str):
        for task in self.tasks.values():
            if finished_task_id in task.dependencies:
                task.dependencies.remove(finished_task_id)
                self._check_dependencies(task)
