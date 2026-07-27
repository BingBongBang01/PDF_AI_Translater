from PySide6.QtCore import QThread, Signal

class BaseWorker(QThread):
    """Base QThread worker for heavy tasks."""
    progress = Signal(int, str)
    error = Signal(str)
    finished = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
