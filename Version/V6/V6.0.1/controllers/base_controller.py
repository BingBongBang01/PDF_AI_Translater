from PySide6.QtCore import QObject

class BaseController(QObject):
    """Base class for all controllers mediating between UI and Services."""
    def __init__(self, parent=None):
        super().__init__(parent)
