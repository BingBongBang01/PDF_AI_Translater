@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"

echo ==========================================
echo PDF Translater V3.4 Windows EXE Builder
echo ==========================================
echo.

echo [1/6] 실제 Python 3.12 경로 확인
set "PYTHON_EXE="
for /f "usebackq delims=" %%I in (`py -3.12 -c "import sys; print(sys.executable)" 2^>nul`) do set "PYTHON_EXE=%%I"

if not defined PYTHON_EXE (
    echo [오류] py launcher에서 Python 3.12를 찾지 못했습니다.
    echo 현재 설치된 Python:
    py -0p
    pause
    exit /b 1
)

if not exist "%PYTHON_EXE%" (
    echo [오류] 실제 Python 실행 파일이 없습니다:
    echo %PYTHON_EXE%
    pause
    exit /b 1
)

echo 사용 Python: %PYTHON_EXE%
echo.

echo [2/6] pip 및 패키지 설치
"%PYTHON_EXE%" -m pip install --upgrade pip
if errorlevel 1 goto :error
"%PYTHON_EXE%" -m pip install --upgrade -r requirements.txt
if errorlevel 1 goto :error

echo.
echo [3/6] 동일 Python 환경의 핵심 모듈 검사
"%PYTHON_EXE%" -c "import sys, pymupdf, pypdf; print('Python:',sys.executable); print('PyMuPDF:',pymupdf.__file__); print('pypdf:',pypdf.__file__)"
if errorlevel 1 goto :error

echo.
echo [4/6] 기존 빌드 삭제
if exist build rmdir /s /q build
if exist "dist\PDF-Translater-v3.6" rmdir /s /q "dist\PDF-Translater-v3.6"

echo.
echo [5/6] PyInstaller 빌드
"%PYTHON_EXE%" -m PyInstaller --noconfirm --clean --onedir --windowed ^
 --name PDF-Translater-v3.6 ^
 --collect-all pymupdf ^
 --collect-all pypdf ^
 --collect-all anthropic ^
 --collect-all google.genai ^
 --collect-all openai ^
 --hidden-import pymupdf ^
 --hidden-import fitz ^
 --hidden-import translate_pdf ^
 --add-data "translate_pdf.py;." ^
 --add-data "requirements.txt;." ^
 --add-data "prompts;prompts" ^
 gui.py
if errorlevel 1 goto :error

echo.
echo [6/6] 빌드 결과 검사
if not exist "dist\PDF-Translater-v3.6\PDF-Translater-v3.6.exe" (
    echo [오류] EXE가 생성되지 않았습니다.
    goto :error
)

echo.
echo ==========================================
echo 빌드 완료
echo dist\PDF-Translater-v3.6\PDF-Translater-v3.6.exe
echo ==========================================
pause
exit /b 0

:error
echo.
echo [오류] 빌드 중 문제가 발생했습니다.
echo 위 로그를 확인해 주세요.
pause
exit /b 1
