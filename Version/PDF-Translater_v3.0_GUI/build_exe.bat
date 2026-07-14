@echo off
chcp 65001 >nul
cd /d "%~dp0"
py -m pip install -r requirements.txt
pyinstaller --noconfirm --clean --onedir --windowed --name PDF-Translater-v2.92 ^
 --add-data "translate_pdf.py;." ^
 --add-data "prompts;prompts" ^
 --hidden-import pymupdf --hidden-import=pypdf ^
 --hidden-import=anthropic --hidden-import=google.genai --hidden-import=openai ^
 gui.py
echo.
echo 완료: dist\PDF-Translater-v2.92\PDF-Translater-v2.92.exe
pause
