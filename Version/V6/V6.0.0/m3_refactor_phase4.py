import os
import re

UI_DIR = r"c:\Users\USER\Documents\github\PDF-Translater\Version\V6\V6.0.0\ui"

# List of widgets to replace
WIDGETS = [
    'QToolButton', 'QPlainTextEdit', 'QTextEdit', 'QSpinBox', 'QDoubleSpinBox',
    'QSlider', 'QCheckBox', 'QRadioButton', 'QGroupBox', 'QFrame', 'QTabWidget',
    'QTreeWidget', 'QTreeView', 'QTableWidget', 'QTableView', 'QListWidget',
    'QListView', 'QMenu', 'QMenuBar', 'QToolBar', 'QDockWidget',
    'QProgressBar', 'QSplitter', 'QScrollArea', 'QScrollBar', 'QLabel'
]

# Note: We already handled QPushButton, QLineEdit, QComboBox, QStatusBar (to MainStatusBar)
# We also have to be careful not to replace QLabel if it's already MaterialLabel, 
# but the script looks for word boundaries.

def process_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    original = content
    added_imports = set()

    for old_widget in WIDGETS:
        new_widget = f"Material{old_widget[1:]}" # e.g. QLabel -> MaterialLabel
        # Check if the old widget is imported or used
        if re.search(rf'\b{old_widget}\b', content):
            # Replace instantiation/usage
            content = re.sub(rf'\b{old_widget}\b', new_widget, content)
            added_imports.add(new_widget)
            
    if content != original:
        if added_imports:
            # We need to add the new imports near the top of the file
            import_str = f"from ui.widgets.m3_components import {', '.join(added_imports)}\n"
            
            # Simple heuristic to add imports after the last PySide6 import
            lines = content.split('\n')
            insert_idx = 0
            for i, line in enumerate(lines):
                if "import" in line and "PySide6" in line:
                    insert_idx = i + 1
                    
            lines.insert(insert_idx, import_str)
            content = "\n".join(lines)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"Refactored Phase 4: {filepath}")

for root, dirs, files in os.walk(UI_DIR):
    if 'themes' in root or '__pycache__' in root:
        continue
    for file in files:
        if file.endswith('.py') and file not in ['m3_components.py', 'm3_text_field.py', 'm3_combo_box.py', 'material_button.py', 'material_card.py', 'action_card.py']:
            process_file(os.path.join(root, file))

print("Phase 4 Refactoring complete.")
