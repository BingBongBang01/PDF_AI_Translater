from PySide6.QtWidgets import QLabel
from PySide6.QtCore import Qt, Signal
from ui.widgets.material_card import MaterialCard

class ActionCard(MaterialCard):
    clicked = Signal()

    def __init__(self, title: str, description: str, parent=None):
        super().__init__(parent, elevation="level1")
        self.setCursor(Qt.PointingHandCursor)
        
        self.lbl_title = QLabel(title)
        self.lbl_title.setProperty('m3_typography', 'title_medium')
        
        self.lbl_desc = QLabel(description)
        self.lbl_desc.setProperty('m3_typography', 'body_medium')
        
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        ds = app.property("m3_design_system") if app else None
        
        if ds:
            self.lbl_title.setStyleSheet(f"color: {ds.colors.on_surface};")
            self.lbl_desc.setStyleSheet(f"color: {ds.colors.on_surface_variant};")
            
            # Hover effect for M3 Action Cards usually elevates or changes surface
            # We append to the base MaterialCard stylesheet
            self.setStyleSheet(self.styleSheet() + f"""
                QFrame#MaterialCard:hover {{
                    background-color: {ds.colors.surface_container_highest};
                }}
            """)
        
        self.layout.addWidget(self.lbl_title)
        self.layout.addWidget(self.lbl_desc)
        self.layout.addStretch()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)
