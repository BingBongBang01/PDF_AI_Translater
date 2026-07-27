from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout
from ui.widgets.m3_components import MaterialLabel, MaterialTextEdit

from ui.widgets.material_button import MaterialButton
from ui.widgets.m3_text_field import MaterialTextField
from utils.i18n import tr


class OcrResultPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(8, 8, 8, 8)

        toolbar = QHBoxLayout()
        self.btn_copy = MaterialButton(tr("Copy"))
        self.btn_select_all = MaterialButton(tr("Select All"))
        self.btn_highlight = MaterialButton(tr("Highlight"))

        self.search_box = MaterialTextField()
        self.search_box.setPlaceholderText(tr("Search result..."))
        
        toolbar.addWidget(self.btn_copy)
        toolbar.addWidget(self.btn_select_all)
        toolbar.addWidget(self.btn_highlight)
        toolbar.addStretch()
        toolbar.addWidget(self.search_box)
        
        self.layout.addLayout(toolbar)
        
        self.result_text = MaterialTextEdit()
        self.result_text.setPlaceholderText(tr("Rich text OCR results will appear here..."))
        self.layout.addWidget(self.result_text)

        # Language/Confidence quick info
        info_layout = QHBoxLayout()
        self.lbl_lang = MaterialLabel(tr("Language: Auto"))
        self.lbl_conf = MaterialLabel(tr("Confidence: --"))
        info_layout.addWidget(self.lbl_lang)
        info_layout.addStretch()
        info_layout.addWidget(self.lbl_conf)
        
        self.layout.addLayout(info_layout)
