from enum import Enum
from dataclasses import dataclass
from typing import List
import queue

class QueueStatus(Enum):
    WAITING = "waiting"
    PREPARING = "preparing"
    RUNNING = "running"
    RETRYING = "retrying"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

@dataclass
class QueueItem:
    chunk_id: str
    priority: int
    status: QueueStatus = QueueStatus.WAITING
    retries: int = 0
    
    # Allows heapq to sort correctly
    def __lt__(self, other):
        return self.priority < other.priority

class TranslationQueue:
    """Thread-safe priority queue for managing translation tasks."""
    def __init__(self):
        self._queue = queue.PriorityQueue()
        self.items = {}
        
    def push(self, item: QueueItem) -> None:
        self.items[item.chunk_id] = item
        self._queue.put(item)
        
    def pop(self) -> QueueItem:
        return self._queue.get()
        
    def update_status(self, chunk_id: str, status: QueueStatus) -> None:
        if chunk_id in self.items:
            self.items[chunk_id].status = status
