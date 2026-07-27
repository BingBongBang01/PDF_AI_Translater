from PySide6.QtWidgets import QWidget, QVBoxLayout
from ui.widgets.m3_components import MaterialTabWidget, MaterialTextEdit
from utils.i18n import tr


class ExportPreviewPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        
        self.tabs = MaterialTabWidget()
        
        # Document Preview
        self.doc_preview = MaterialTextEdit()
        self.doc_preview.setReadOnly(True)
        self.doc_preview.setPlaceholderText("Mock Document preview rendering...")
        
        # Metadata Preview
        self.meta_preview = MaterialTextEdit()
        self.meta_preview.setReadOnly(True)
        self.meta_preview.setPlaceholderText("Mock Metadata dictionary preview...")
        
        # Layout Preview
        self.layout_preview = MaterialTextEdit()
        self.layout_preview.setReadOnly(True)
        self.layout_preview.setPlaceholderText("Mock bounding box and layout visualization...")
        
        # Watermark Preview
        self.watermark_preview = MaterialTextEdit()
        self.watermark_preview.setReadOnly(True)
        self.watermark_preview.setPlaceholderText("Mock Watermark rendering...")
        
        self.tabs.addTab(self.doc_preview, tr("Document"))
        self.tabs.addTab(self.meta_preview, tr("Metadata"))
        self.tabs.addTab(self.layout_preview, tr("Layout"))
        self.tabs.addTab(self.watermark_preview, tr("Watermark"))
        
        self.layout.addWidget(self.tabs)
        
    def load_mock_preview(self, format_name):
        self.doc_preview.setHtml(f"<h3>Previewing {format_name}</h3><p>This is a rendered mock preview of the export target.</p>")
        self.meta_preview.setText(f'{{\n  "format": "{format_name}",\n  "author": "PDF Translater",\n  "pages": 14\n}}')
        self.layout_preview.setText(f"Layout engine processing for {format_name}...\nHeader applied.\nMargins calculated.")
        self.watermark_preview.setText(f"Watermark overlay applied to {format_name} layers.")
