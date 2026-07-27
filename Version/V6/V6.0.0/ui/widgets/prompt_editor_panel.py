from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout
from ui.widgets.m3_components import MaterialTextEdit

from ui.widgets.material_button import MaterialButton


class PromptEditorPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(8, 8, 8, 8)
        
        toolbar = QHBoxLayout()
        self.btn_reset = MaterialButton("Reset to Default")
        self.btn_preview = MaterialButton("Preview Prompt")
        toolbar.addWidget(self.btn_reset)
        toolbar.addWidget(self.btn_preview)
        toolbar.addStretch()
        
        self.layout.addLayout(toolbar)
        
        self.te_prompt = MaterialTextEdit()
        self.te_prompt.setPlaceholderText("Enter custom system prompt with {source_lang} and {target_lang} variables...")
        self.te_prompt.setText("Translate the following text from {source_lang} to {target_lang}. Preserve all formatting.")
        self.layout.addWidget(self.te_prompt)
