from ui.windows.base_page import BasePage

from ui.widgets.m3_components import MaterialLabel


class AboutPage(BasePage):
    def setup_ui(self):
        lbl = MaterialLabel("About Page (Placeholder)\nVersion 6.0.0")
        lbl.setStyleSheet("font-size: 24px;")
        self.layout.addWidget(lbl)
        self.layout.addStretch()
