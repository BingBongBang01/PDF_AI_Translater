from PySide6.QtWidgets import QComboBox, QApplication

class MaterialComboBox(QComboBox):
    """Reusable Material Design 3 ComboBox."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty('m3_typography', 'body_large')
        self._apply_m3_style()
        
    def _apply_m3_style(self):
        app = QApplication.instance()
        ds = app.property("m3_design_system") if app else None
        if ds:
            c = ds.colors
            s = ds.shape
            self.setStyleSheet(f"""
                QComboBox {{
                    background-color: {c.surface_variant};
                    border: none;
                    border-bottom: 2px solid {c.outline};
                    padding: 8px 16px;
                    border-radius: {s.extra_small} {s.extra_small} 0 0;
                    color: {c.on_surface};
                }}
                QComboBox:hover {{
                    background-color: {c.hover};
                }}
                QComboBox::drop-down {{
                    border: none;
                }}
            """)
