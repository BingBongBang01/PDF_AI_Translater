from PySide6.QtWidgets import QDialog, QVBoxLayout

class BaseDialog(QDialog):
    """Base class for Material Design styled dialogs."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.setup_ui()

    def setup_ui(self):
        pass
