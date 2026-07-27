from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout
from ui.widgets.material_button import MaterialButton
from ui.widgets.m3_text_field import MaterialTextField

from ui.widgets.glossary_table import GlossaryTable

class GlossaryManagerPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(8, 8, 8, 8)
        
        toolbar = QHBoxLayout()
        self.btn_add = MaterialButton("Add")
        self.btn_edit = MaterialButton("Edit")
        self.btn_delete = MaterialButton("Delete")
        self.btn_import = MaterialButton("Import")
        self.btn_export = MaterialButton("Export")
        
        self.search_box = MaterialTextField()
        self.search_box.setPlaceholderText("Search Glossary...")
        
        toolbar.addWidget(self.btn_add)
        toolbar.addWidget(self.btn_edit)
        toolbar.addWidget(self.btn_delete)
        toolbar.addWidget(self.btn_import)
        toolbar.addWidget(self.btn_export)
        toolbar.addStretch()
        toolbar.addWidget(self.search_box)
        
        self.layout.addLayout(toolbar)
        
        self.glossary_table = GlossaryTable()
        self.layout.addWidget(self.glossary_table)
