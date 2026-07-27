import os
import re

UI_DIR = r"c:\Users\USER\Documents\github\PDF-Translater\Version\V6\V6.0.0\ui"

REPLACEMENTS = {
    'QPushButton': ('MaterialButton', 'ui.widgets.material_button'),
    'QLineEdit': ('MaterialTextField', 'ui.widgets.m3_text_field'),
    'QComboBox': ('MaterialComboBox', 'ui.widgets.m3_combo_box'),
    # Note: replacing QFrame with MaterialCard might be too aggressive if they just want a standard QFrame,
    # but the instructions say "No default Qt frames... Replace every default widget with the project's Material component."
}

def process_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    original = content
    added_imports = set()

    for old_widget, (new_widget, module) in REPLACEMENTS.items():
        # Only replace if the old widget is used
        if re.search(rf'\b{old_widget}\b', content):
            # Replace instantiation/usage
            content = re.sub(rf'\b{old_widget}\b', new_widget, content)
            added_imports.add(f"from {module} import {new_widget}")
            
    if content != original:
        # We need to add the new imports near the top of the file
        import_str = "\n".join(added_imports) + "\n"
        
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
        print(f"Refactored: {filepath}")

for root, dirs, files in os.walk(UI_DIR):
    # skip some directories if needed
    if 'themes' in root or '__pycache__' in root:
        continue
    for file in files:
        if file.endswith('.py') and file not in ['m3_text_field.py', 'm3_combo_box.py', 'material_button.py', 'material_card.py', 'action_card.py']:
            process_file(os.path.join(root, file))

print("Refactoring complete.")
