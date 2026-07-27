from PySide6.QtGui import QColor, QFont, QPalette
from dataclasses import dataclass
from typing import Dict, Any

@dataclass
class M3Colors:
    primary: str
    on_primary: str
    primary_container: str
    on_primary_container: str
    secondary: str
    on_secondary: str
    secondary_container: str
    on_secondary_container: str
    tertiary: str
    on_tertiary: str
    tertiary_container: str
    on_tertiary_container: str
    error: str
    on_error: str
    error_container: str
    on_error_container: str
    background: str
    on_background: str
    surface: str
    on_surface: str
    surface_variant: str
    on_surface_variant: str
    outline: str
    outline_variant: str
    shadow: str
    scrim: str
    inverse_surface: str
    inverse_on_surface: str
    inverse_primary: str
    
    # Surface Tones (Elevation)
    surface_container_highest: str
    surface_container_high: str
    surface_container: str
    surface_container_low: str
    surface_container_lowest: str
    
    # State Layers
    hover: str
    pressed: str
    dragged: str


M3_LIGHT = M3Colors(
    primary="#6750A4",
    on_primary="#FFFFFF",
    primary_container="#EADDFF",
    on_primary_container="#21005D",
    secondary="#625B71",
    on_secondary="#FFFFFF",
    secondary_container="#E8DEF8",
    on_secondary_container="#1D192B",
    tertiary="#7D5260",
    on_tertiary="#FFFFFF",
    tertiary_container="#FFD8E4",
    on_tertiary_container="#31111D",
    error="#B3261E",
    on_error="#FFFFFF",
    error_container="#F9DEDC",
    on_error_container="#410E0B",
    background="#FEF7FF",
    on_background="#1D1B20",
    surface="#FEF7FF",
    on_surface="#1D1B20",
    surface_variant="#E7E0EC",
    on_surface_variant="#49454F",
    outline="#79747E",
    outline_variant="#CAC4D0",
    shadow="#000000",
    scrim="#000000",
    inverse_surface="#322F35",
    inverse_on_surface="#F5EFF7",
    inverse_primary="#D0BCFF",
    
    surface_container_highest="#E6E0E9",
    surface_container_high="#ECE6F0",
    surface_container="#F3EDF7",
    surface_container_low="#F7F2FA",
    surface_container_lowest="#FFFFFF",
    
    hover="rgba(29, 27, 32, 0.08)",
    pressed="rgba(29, 27, 32, 0.12)",
    dragged="rgba(29, 27, 32, 0.16)",
)

M3_DARK = M3Colors(
    primary="#D0BCFF",
    on_primary="#381E72",
    primary_container="#4F378B",
    on_primary_container="#EADDFF",
    secondary="#CCC2DC",
    on_secondary="#332D41",
    secondary_container="#4A4458",
    on_secondary_container="#E8DEF8",
    tertiary="#EFB8C8",
    on_tertiary="#492532",
    tertiary_container="#633B48",
    on_tertiary_container="#FFD8E4",
    error="#F2B8B5",
    on_error="#601410",
    error_container="#8C1D18",
    on_error_container="#F9DEDC",
    background="#141218",
    on_background="#E6E0E9",
    surface="#141218",
    on_surface="#E6E0E9",
    surface_variant="#49454F",
    on_surface_variant="#CAC4D0",
    outline="#938F99",
    outline_variant="#49454F",
    shadow="#000000",
    scrim="#000000",
    inverse_surface="#E6E0E9",
    inverse_on_surface="#322F35",
    inverse_primary="#6750A4",
    
    surface_container_highest="#36343B",
    surface_container_high="#2B2930",
    surface_container="#211F26",
    surface_container_low="#1D1B20",
    surface_container_lowest="#0F0D13",
    
    hover="rgba(230, 224, 233, 0.08)",
    pressed="rgba(230, 224, 233, 0.12)",
    dragged="rgba(230, 224, 233, 0.16)",
)

@dataclass
class M3Typography:
    font_family = "Inter, Roboto, 'Segoe UI', sans-serif"
    display_large = f"font-family: {font_family}; font-size: 57px; font-weight: 400; letter-spacing: -0.25px; line-height: 64px;"
    display_medium = f"font-family: {font_family}; font-size: 45px; font-weight: 400; letter-spacing: 0px; line-height: 52px;"
    display_small = f"font-family: {font_family}; font-size: 36px; font-weight: 400; letter-spacing: 0px; line-height: 44px;"
    headline_large = f"font-family: {font_family}; font-size: 32px; font-weight: 400; letter-spacing: 0px; line-height: 40px;"
    headline_medium = f"font-family: {font_family}; font-size: 28px; font-weight: 400; letter-spacing: 0px; line-height: 36px;"
    headline_small = f"font-family: {font_family}; font-size: 24px; font-weight: 400; letter-spacing: 0px; line-height: 32px;"
    title_large = f"font-family: {font_family}; font-size: 22px; font-weight: 400; letter-spacing: 0px; line-height: 28px;"
    title_medium = f"font-family: {font_family}; font-size: 16px; font-weight: 500; letter-spacing: 0.15px; line-height: 24px;"
    title_small = f"font-family: {font_family}; font-size: 14px; font-weight: 500; letter-spacing: 0.1px; line-height: 20px;"
    body_large = f"font-family: {font_family}; font-size: 16px; font-weight: 400; letter-spacing: 0.5px; line-height: 24px;"
    body_medium = f"font-family: {font_family}; font-size: 14px; font-weight: 400; letter-spacing: 0.25px; line-height: 20px;"
    body_small = f"font-family: {font_family}; font-size: 12px; font-weight: 400; letter-spacing: 0.4px; line-height: 16px;"
    label_large = f"font-family: {font_family}; font-size: 14px; font-weight: 500; letter-spacing: 0.1px; line-height: 20px;"
    label_medium = f"font-family: {font_family}; font-size: 12px; font-weight: 500; letter-spacing: 0.5px; line-height: 16px;"
    label_small = f"font-family: {font_family}; font-size: 11px; font-weight: 500; letter-spacing: 0.5px; line-height: 16px;"

@dataclass
class M3Shape:
    extra_small = "4px"
    small = "8px"
    medium = "12px"
    large = "16px"
    extra_large = "28px"
    full = "50%" # usually for fully rounded buttons

@dataclass
class M3Elevation:
    level0 = "none"
    level1 = "0px 1px 2px 0px rgba(0,0,0,0.3), 0px 1px 3px 1px rgba(0,0,0,0.15)"
    level2 = "0px 1px 2px 0px rgba(0,0,0,0.3), 0px 2px 6px 2px rgba(0,0,0,0.15)"
    level3 = "0px 1px 3px 0px rgba(0,0,0,0.3), 0px 4px 8px 3px rgba(0,0,0,0.15)"
    level4 = "0px 2px 3px 0px rgba(0,0,0,0.3), 0px 6px 10px 4px rgba(0,0,0,0.15)"
    level5 = "0px 4px 4px 0px rgba(0,0,0,0.3), 0px 8px 12px 6px rgba(0,0,0,0.15)"

class M3DesignSystem:
    def __init__(self, is_dark=False):
        self.is_dark = is_dark
        self.colors = M3_DARK if is_dark else M3_LIGHT
        self.typography = M3Typography()
        self.shape = M3Shape()
        self.elevation = M3Elevation()

    def generate_qss(self) -> str:
        # Base QSS stylesheet for the application
        c = self.colors
        t = self.typography
        s = self.shape
        
        qss = f"""
        /* ---------------------------------------------------------
           MATERIAL DESIGN 3 GLOBAL QSS
        --------------------------------------------------------- */
        
        QWidget {{
            font-family: {M3Typography.font_family};
            font-size: 14px;
            color: {c.on_surface};
            background-color: transparent;
        }}
        
        QMainWindow, QDialog {{
            background-color: {c.background};
        }}
        
        /* Typography Classes */
        QLabel[m3_typography="display_large"] {{ {t.display_large} }}
        QLabel[m3_typography="display_medium"] {{ {t.display_medium} }}
        QLabel[m3_typography="display_small"] {{ {t.display_small} }}
        QLabel[m3_typography="headline_large"] {{ {t.headline_large} }}
        QLabel[m3_typography="headline_medium"] {{ {t.headline_medium} }}
        QLabel[m3_typography="headline_small"] {{ {t.headline_small} }}
        QLabel[m3_typography="title_large"] {{ {t.title_large} }}
        QLabel[m3_typography="title_medium"] {{ {t.title_medium} }}
        QLabel[m3_typography="title_small"] {{ {t.title_small} }}
        QLabel[m3_typography="body_large"] {{ {t.body_large} }}
        QLabel[m3_typography="body_medium"] {{ {t.body_medium} }}
        QLabel[m3_typography="body_small"] {{ {t.body_small} }}
        QLabel[m3_typography="label_large"] {{ {t.label_large} }}
        QLabel[m3_typography="label_medium"] {{ {t.label_medium} }}
        QLabel[m3_typography="label_small"] {{ {t.label_small} }}
        
        /* General scrollbars */
        QScrollBar:vertical {{
            border: none;
            background: transparent;
            width: 10px;
            margin: 0px 0 0px 0;
            border-radius: {s.extra_small};
        }}
        QScrollBar::handle:vertical {{
            background: {c.outline_variant};
            min-height: 20px;
            border-radius: {s.extra_small};
        }}
        QScrollBar::handle:vertical:hover {{
            background: {c.outline};
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            border: none;
            background: none;
            height: 0px;
        }}
        QScrollBar:horizontal {{
            border: none;
            background: transparent;
            height: 10px;
            margin: 0px 0 0px 0;
            border-radius: {s.extra_small};
        }}
        QScrollBar::handle:horizontal {{
            background: {c.outline_variant};
            min-width: 20px;
            border-radius: {s.extra_small};
        }}
        QScrollBar::handle:horizontal:hover {{
            background: {c.outline};
        }}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
            border: none;
            background: none;
            width: 0px;
        }}
        
        /* CheckBoxes */
        QCheckBox {{
            spacing: 8px;
            {t.body_medium}
        }}
        QCheckBox::indicator {{
            width: 18px;
            height: 18px;
            border-radius: 2px;
            border: 2px solid {c.on_surface_variant};
        }}
        QCheckBox::indicator:unchecked:hover {{
            background-color: {c.hover};
        }}
        QCheckBox::indicator:checked {{
            background-color: {c.primary};
            border: 2px solid {c.primary};
            image: url(assets/icons/check.svg); /* Requires icon! */
        }}
        QCheckBox::indicator:checked:hover {{
            background-color: {c.primary};
            border: 2px solid {c.primary};
        }}
        
        /* RadioButtons */
        QRadioButton {{
            spacing: 8px;
            {t.body_medium}
        }}
        QRadioButton::indicator {{
            width: 18px;
            height: 18px;
            border-radius: 10px;
            border: 2px solid {c.on_surface_variant};
        }}
        QRadioButton::indicator:unchecked:hover {{
            background-color: {c.hover};
        }}
        QRadioButton::indicator:checked {{
            background-color: transparent;
            border: 2px solid {c.primary};
            image: url(assets/icons/radio_checked.svg); /* Placeholder */
        }}
        
        /* Combo Boxes */
        QComboBox {{
            border: 1px solid {c.outline};
            border-radius: {s.extra_small};
            padding: 8px 16px;
            min-height: 32px;
            background-color: {c.surface};
            {t.body_large}
        }}
        QComboBox:hover {{
            background-color: {c.surface_variant};
        }}
        QComboBox::drop-down {{
            subcontrol-origin: padding;
            subcontrol-position: top right;
            width: 24px;
            border-left-width: 0px;
        }}
        
        /* GroupBox */
        QGroupBox {{
            border: 1px solid {c.outline_variant};
            border-radius: {s.medium};
            margin-top: 24px;
            {t.title_medium}
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            subcontrol-position: top left;
            padding: 0 8px;
            left: 16px;
        }}
        """
        return qss

global_design_system = M3DesignSystem()
