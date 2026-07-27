from PySide6.QtWidgets import QVBoxLayout, QButtonGroup, QApplication, QSizePolicy
from PySide6.QtCore import Signal, Qt
from ui.widgets.m3_components import MaterialFrame
from ui.widgets.material_button import MaterialButton

class NavigationRail(MaterialFrame):
    """Left navigation rail with icons."""
    page_changed = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("NavigationRail")
        self.setMinimumWidth(88)
        self.setMaximumWidth(260)
        self.resize(110, self.height())
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        self.setStyleSheet("") # Clear static CSS
        self._apply_m3_style()

    def _apply_m3_style(self):
        app = QApplication.instance()
        design_system = app.property("m3_design_system") if app else None
        
        if design_system:
            c = design_system.colors
            s = design_system.shape
            
            self.setStyleSheet(f"""
                MaterialFrame#NavigationRail {{
                    background-color: {c.surface_container};
                    border-right: 1px solid {c.outline_variant};
                }}
                MaterialButton {{
                    border: none;
                    padding: 10px;
                    border-radius: {s.extra_large}; /* M3 pills are very round */
                    color: {c.on_surface_variant};
                }}
                MaterialButton:hover {{
                    background-color: {c.hover};
                }}
                MaterialButton:checked {{
                    background-color: {c.secondary_container};
                    color: {c.on_secondary_container};
                }}
            """)
        
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(8, 24, 8, 24)
        self.layout.setSpacing(12)
        
        self.btn_group = QButtonGroup(self)
        self.btn_group.setExclusive(True)
        self.btn_group.idClicked.connect(self.page_changed.emit)

        self.layout.addStretch()

    def add_destination(self, icon_name: str, tooltip: str, page_id: int):
        btn = MaterialButton(icon_name) # Placeholder for actual icons
        btn.setToolTip(tooltip)
        btn.setCheckable(True)
        btn.setCursor(Qt.PointingHandCursor)
        self.btn_group.addButton(btn, page_id)
        
        # Insert before the stretch
        self.layout.insertWidget(self.layout.count() - 1, btn)
        
        if self.btn_group.buttons() and len(self.btn_group.buttons()) == 1:
            btn.setChecked(True)
