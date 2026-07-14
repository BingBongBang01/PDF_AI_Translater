@echo off
chcp 65001 >nul
cd /d "%~dp0"

net session >nul 2>&1
if %errorlevel% neq 0 (
  echo 관리자 권한으로 다시 실행합니다...
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)

echo [1/4] Python 확인
py --version || goto :error

echo [2/4] 패키지 설치/업데이트
py -m pip install --upgrade pip
py -m pip install --upgrade -r requirements.txt
py -c "import pymupdf; print('PyMuPDF OK:', pymupdf.__file__)" || goto :error

echo [3/4] 기존 빌드 삭제
if exist build rmdir /s /q build
if exist "dist\PDF-Translater-v3.3" rmdir /s /q "dist\PDF-Translater-v3.3"

echo [4/4] EXE 빌드
py -m PyInstaller --noconfirm --clean --onedir --windowed --uac-admin ^
 --name PDF-Translater-v3.3 ^
 --collect-all pymupdf ^
 --collect-all pypdf ^
 --collect-all anthropic ^
 --collect-all google.genai ^
 --collect-all openai ^
 --hidden-import pymupdf ^
 --hidden-import fitz ^
 --hidden-import translate_pdf ^
 --add-data "translate_pdf.py;." ^
 --add-data "prompts;prompts" ^
 gui.py
if %errorlevel% neq 0 goto :error

echo.
echo 완료: dist\PDF-Translater-v3.3\PDF-Translater-v3.3.exe
pause
exit /b 0

:error
echo.
echo 빌드 중 오류가 발생했습니다.
pause
exit /b 1
