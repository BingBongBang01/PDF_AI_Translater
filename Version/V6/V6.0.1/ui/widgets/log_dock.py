from PySide6.QtWidgets import QVBoxLayout, QWidget, QHBoxLayout
from ui.widgets.m3_components import MaterialTextEdit, MaterialDockWidget

from ui.widgets.material_button import MaterialButton


class LogDock(MaterialDockWidget):
    """Bottom log viewer dock."""
    def __init__(self, title="Logs", parent=None):
        super().__init__(title, parent)
        self.setAllowedAreas(from_module("PySide6.QtCore").Qt.BottomDockWidgetArea)
        
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        
        toolbar = QHBoxLayout()
        self.btn_clear = MaterialButton("Clear")
        self.btn_copy = MaterialButton("Copy")
        toolbar.addWidget(self.btn_clear)
        toolbar.addWidget(self.btn_copy)
        toolbar.addStretch()
        
        self.text_edit = MaterialTextEdit()
        self.text_edit.setReadOnly(True)
        from PySide6.QtWidgets import QSizePolicy
        self.text_edit.setMinimumHeight(50)
        self.text_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        container.setMinimumHeight(50)
        
        layout.addLayout(toolbar)
        layout.addWidget(self.text_edit)
        
        self.setWidget(container)
        
        self.btn_clear.clicked.connect(self.text_edit.clear)
        self.btn_copy.clicked.connect(self.text_edit.selectAll) # Simplified copy

    def log_info(self, text: str):
        self.text_edit.append(f"<span style='color: white;'>[INFO] {text}</span>")
        
    def log_error(self, text: str):
        self.text_edit.append(f"<span style='color: red;'>[ERROR] {text}</span>")

def from_module(module_name):
    import importlib
    return importlib.import_module(module_name)
