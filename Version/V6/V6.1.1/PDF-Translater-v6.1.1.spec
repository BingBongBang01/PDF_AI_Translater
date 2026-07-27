# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files

datas = [('translate_pdf.py', '.'), ('pdf_engine', 'pdf_engine'), ('requirements.txt', '.'), ('prompts', 'prompts')]
datas += collect_data_files('customtkinter')


a = Analysis(
    ['gui.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=['pymupdf', 'fitz', 'translate_pdf', 'pdf_engine', 'pdf_engine.config', 'pdf_engine.segment', 'pdf_engine.extraction', 'pdf_engine.batching', 'pdf_engine.providers_cloud', 'pdf_engine.providers_local', 'pdf_engine.scheduler', 'pdf_engine.rendering', 'pdf_engine.io_utils', 'pdf_engine.filenaming', 'pdf_engine.cache'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['scipy', 'matplotlib', 'pandas', 'torch', 'torchvision', 'IPython', 'jupyter', 'pytest', 'unittest', 'tkinter.test'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='PDF-Translater-v6.1.1',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
