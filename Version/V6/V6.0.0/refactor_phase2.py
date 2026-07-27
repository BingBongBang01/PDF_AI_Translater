import os
import shutil
from pathlib import Path

ROOT = Path(r"c:\Users\USER\Documents\github\PDF-Translater\Version\V6\V6.0.0")
PDF_ENGINE = ROOT / "pdf_engine"

MOVES = {
    "extraction.py": ROOT / "services" / "pdf" / "extraction.py",
    "rendering.py": ROOT / "services" / "pdf" / "rendering.py",
    "batching.py": ROOT / "services" / "translator" / "batching.py",
    "scheduler.py": ROOT / "services" / "translator" / "scheduler.py",
    "providers_cloud.py": ROOT / "services" / "translator" / "providers_cloud.py",
    "providers_local.py": ROOT / "services" / "translator" / "providers_local.py",
    "manga_ocr_engine.py": ROOT / "services" / "ocr" / "manga_ocr_engine.py",
    "config.py": ROOT / "config" / "config.py",
    "segment.py": ROOT / "models" / "segment.py",
    "io_utils.py": ROOT / "utils" / "io_utils.py",
    "filenaming.py": ROOT / "utils" / "filenaming.py",
    "__init__.py": None  # Delete
}

MODULE_MAP = {
    "extraction": "services.pdf.extraction",
    "rendering": "services.pdf.rendering",
    "batching": "services.translator.batching",
    "scheduler": "services.translator.scheduler",
    "providers_cloud": "services.translator.providers_cloud",
    "providers_local": "services.translator.providers_local",
    "manga_ocr_engine": "services.ocr.manga_ocr_engine",
    "config": "config.config",
    "segment": "models.segment",
    "io_utils": "utils.io_utils",
    "filenaming": "utils.filenaming",
}

for src_name, dst_path in MOVES.items():
    src_file = PDF_ENGINE / src_name
    if src_file.exists():
        if dst_path is None:
            src_file.unlink()
        else:
            dst_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src_file), str(dst_path))

for p in [ROOT/"services", ROOT/"services"/"pdf", ROOT/"services"/"translator", ROOT/"services"/"ocr", ROOT/"services"/"export", ROOT/"config", ROOT/"models", ROOT/"utils"]:
    p.mkdir(parents=True, exist_ok=True)
    (p / "__init__.py").touch()

def update_imports(filepath):
    content = filepath.read_text(encoding="utf-8")
    
    for old_mod, new_mod in MODULE_MAP.items():
        content = content.replace(f"from pdf_engine.{old_mod} import", f"from {new_mod} import")
        content = content.replace(f"import pdf_engine.{old_mod}", f"import {new_mod}")
        content = content.replace(f"from .{old_mod} import", f"from {new_mod} import")
        content = content.replace(f"from . import {old_mod}", f"import {new_mod} as {old_mod}")

    # Fix hardcoded paths
    content = content.replace('APP_DIR / "pdf_engine" / "config.py"', 'APP_DIR / "config" / "config.py"')
    content = content.replace('pdf_engine/', 'services/')

    filepath.write_text(content, encoding="utf-8")

for p in ROOT.rglob("*.py"):
    if "venv" not in p.parts and ".git" not in p.parts and "refactor_phase2.py" not in p.name:
        update_imports(p)

print("Refactoring complete.")
