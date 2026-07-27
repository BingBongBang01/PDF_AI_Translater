from PySide6.QtWidgets import QWidget, QVBoxLayout

class BasePage(QWidget):
    """Base class for all application pages in the stacked widget."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(16, 16, 16, 16)
        self.layout.setSpacing(16)
        self.setup_ui()

    def setup_ui(self):
        """Override to build UI components."""
        pass

    def on_show(self):
        """Called when the page becomes the active page."""
        pass
