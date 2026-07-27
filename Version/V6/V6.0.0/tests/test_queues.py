import pytest
from core.worker_manager import WorkerManager

def test_worker_manager_stress():
    wm = WorkerManager()
    # Verify pool bounds
    assert wm.thread_pool.maxThreadCount() > 0
