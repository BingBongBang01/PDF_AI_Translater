from PySide6.QtWidgets import QFrame, QVBoxLayout, QApplication
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QGraphicsDropShadowEffect

class MaterialCard(QFrame):
    """Reusable Material Design 3 Card with elevation."""
    def __init__(self, parent=None, elevation="level1"):
        super().__init__(parent)
        self.setObjectName("MaterialCard")
        
        # Default M3 Styling
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(16, 16, 16, 16)
        
        # Apply styling dynamically from global system
        self._apply_m3_style(elevation)
        
    def _apply_m3_style(self, elevation):
        app = QApplication.instance()
        design_system = app.property("m3_design_system") if app else None
        
        if design_system:
            c = design_system.colors
            s = design_system.shape
            
            # Surface color mapping based on elevation
            bg_color = c.surface
            if elevation == "level1": bg_color = c.surface_container_low
            elif elevation == "level2": bg_color = c.surface_container
            elif elevation == "level3": bg_color = c.surface_container_high
            elif elevation == "level4": bg_color = c.surface_container_highest
            
            self.setStyleSheet(f"""
                QFrame#MaterialCard {{
                    background-color: {bg_color};
                    border-radius: {s.medium};
                    border: 1px solid {c.outline_variant};
                }}
            """)
            
            # Optional: Apply QGraphicsDropShadowEffect for real shadows
            # but M3 often relies on surface color differences rather than huge drop shadows.
            if elevation != "level0":
                shadow = QGraphicsDropShadowEffect(self)
                shadow.setBlurRadius(10)
                shadow.setColor(QColor(0, 0, 0, 40)) # approximate
                shadow.setOffset(0, 2)
                self.setGraphicsEffect(shadow)

