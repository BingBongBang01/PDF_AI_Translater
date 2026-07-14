@echo off
chcp 65001 >nul
cd /d "%~dp0"
py -m pip install -r requirements.txt
pyinstaller --noconfirm --clean --onedir --windowed --name PDF-Translater-v3.1 ^
 --collect-all pymupdf --collect-all pypdf ^
 --collect-all anthropic --collect-all google.genai --collect-all openai ^
 --hidden-import translate_pdf ^
 --add-data "translate_pdf.py;." ^
 --add-data "prompts;prompts" ^
 gui.py
echo.
echo 완료: dist\PDF-Translater-v3.1\PDF-Translater-v3.1.exe
pause
