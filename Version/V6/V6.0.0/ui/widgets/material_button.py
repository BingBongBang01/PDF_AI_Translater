from PySide6.QtWidgets import QPushButton
from PySide6.QtGui import QCursor
from PySide6.QtCore import Qt

class MaterialButton(QPushButton):
    """Reusable Material Design 3 Button."""
    def __init__(self, text="", parent=None, style_type="filled"):
        super().__init__(text, parent)
        self.style_type = style_type
        
        # Base M3 Typography
        self.setProperty('m3_typography', 'label_large')
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self.setMinimumHeight(40)
        
        # We can dynamically apply QSS based on style_type.
        if style_type == "filled":
            pass # Inherits from global M3 QSS for QPushButton if we define it
        elif style_type == "outlined":
            pass
        elif style_type == "text":
            self.setStyleSheet("background-color: transparent; border: none;")

