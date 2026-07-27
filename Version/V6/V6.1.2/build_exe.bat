@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"

echo =======================================================
echo PDF Translater Windows EXE Builder (Slim Single File)
echo =======================================================
echo.

echo [1/8] Locate base Python interpreter...
set "BASE_PYTHON="

for /f "delims=" %%I in ('py -3 -c "import sys; print(sys.executable)" 2^>nul') do (
    echo %%I | findstr /i "WindowsApps" >nul
    if errorlevel 1 set "BASE_PYTHON=%%I"
)

if not defined BASE_PYTHON (
    for /f "delims=" %%I in ('python -c "import sys; print(sys.executable)" 2^>nul') do (
        echo %%I | findstr /i "WindowsApps" >nul
        if errorlevel 1 set "BASE_PYTHON=%%I"
    )
)

if not defined BASE_PYTHON (
    for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do (
        if exist "%%D\python.exe" set "BASE_PYTHON=%%D\python.exe"
    )
)

if not defined BASE_PYTHON (
    echo [ERROR] Could not locate a valid Python interpreter.
    pause
    exit /b 1
)

echo Using Base Python: %BASE_PYTHON%
echo.

echo [2/8] Read app version...
set "APP_VERSION="
for /f "usebackq delims=" %%V in (`"%BASE_PYTHON%" _get_version.py 2^>nul`) do set "APP_VERSION=%%V"

if not defined APP_VERSION (
    echo [ERROR] Could not read __version__.
    pause
    exit /b 1
)

set "APP_NAME=PDF-Translater-v%APP_VERSION%"
echo App version: %APP_VERSION%
echo Build name : %APP_NAME%
echo.

echo [3/8] Creating/Preparing isolated slim virtual environment (.venv-build)...
if not exist ".venv-build\Scripts\python.exe" (
    "%BASE_PYTHON%" -m venv .venv-build
    if errorlevel 1 goto :error
)

set "VENV_PYTHON=.venv-build\Scripts\python.exe"

echo [4/8] Installing minimal requirements in isolated environment...
"%VENV_PYTHON%" -m pip install --upgrade pip
if errorlevel 1 goto :error
"%VENV_PYTHON%" -m pip install --upgrade -r requirements.txt
if errorlevel 1 goto :error
"%VENV_PYTHON%" -m pip install --upgrade pyinstaller
if errorlevel 1 goto :error

echo.
echo [5/8] Verify core modules in build environment...
"%VENV_PYTHON%" -c "import sys, pymupdf, pypdf, customtkinter; print('Build Python:',sys.executable)"
if errorlevel 1 goto :error

echo.
echo [6/8] Clean previous build artifacts...
if exist build rmdir /s /q build
if exist "dist\%APP_NAME%.exe" del /q "dist\%APP_NAME%.exe"
if exist "%APP_NAME%.spec" del /q "%APP_NAME%.spec"

echo.
echo [7/8] PyInstaller Slim Build...
 "%VENV_PYTHON%" -m PyInstaller --noconfirm --clean --onefile --windowed ^
 --name "%APP_NAME%" ^
 --icon "icon.ico" ^
 --collect-data customtkinter ^
 --hidden-import pymupdf ^
 --hidden-import fitz ^
 --hidden-import translate_pdf ^
 --hidden-import pdf_engine ^
 --hidden-import pdf_engine.config ^
 --hidden-import pdf_engine.segment ^
 --hidden-import pdf_engine.extraction ^
 --hidden-import pdf_engine.batching ^
 --hidden-import pdf_engine.providers_cloud ^
 --hidden-import pdf_engine.providers_local ^
 --hidden-import pdf_engine.scheduler ^
 --hidden-import pdf_engine.rendering ^
 --hidden-import pdf_engine.io_utils ^
 --hidden-import pdf_engine.filenaming ^
 --hidden-import pdf_engine.cache ^
 --exclude-module scipy ^
 --exclude-module matplotlib ^
 --exclude-module pandas ^
 --exclude-module torch ^
 --exclude-module torchvision ^
 --exclude-module IPython ^
 --exclude-module jupyter ^
 --exclude-module pytest ^
 --exclude-module unittest ^
 --exclude-module tkinter.test ^
 --add-data "translate_pdf.py;." ^
 --add-data "pdf_engine;pdf_engine" ^
 --add-data "requirements.txt;." ^
 --add-data "prompts;prompts" ^
 --add-data "icon.ico;." ^
 --add-data "icon.png;." ^
 gui.py
if errorlevel 1 goto :error

echo.
echo [8/8] Verify build result and check file size...
if not exist "dist\%APP_NAME%.exe" (
    echo [ERROR] EXE was not created.
    goto :error
)

for %%F in ("dist\%APP_NAME%.exe") do (
    set /a "SIZE_MB=%%~zF / 1048576"
)

echo.
echo =======================================================
echo Build SUCCESS!
echo Output EXE : dist\%APP_NAME%.exe
echo File Size  : %SIZE_MB% MB
echo =======================================================
pause
exit /b 0

:error
echo.
echo [ERROR] Build failed. Please check the log above.
pause
exit /b 1
