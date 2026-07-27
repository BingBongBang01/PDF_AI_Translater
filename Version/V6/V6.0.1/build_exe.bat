@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"

echo ==========================================
echo PDF Translater Windows EXE Builder (onefile)
echo ==========================================
echo.

set "PYTHON_EXE="
for /f "usebackq delims=" %%I in (`py -3.12 -c "import sys; print(sys.executable)" 2^>nul`) do set "PYTHON_EXE=%%I"

if not defined PYTHON_EXE (
    echo [ERROR] py launcher could not find Python 3.12.
    exit /b 1
)

set "APP_VERSION=6.0.1"
set "APP_NAME=PDF-Translater-v%APP_VERSION%"

echo [1/4] Install pip packages
"%PYTHON_EXE%" -m pip install --upgrade pip pyinstaller pytest
"%PYTHON_EXE%" -m pip install -r requirements.txt

echo [2/4] Clean previous build
if exist build rmdir /s /q build
if exist "dist\%APP_NAME%.exe" del /q "dist\%APP_NAME%.exe"
if exist "%APP_NAME%.spec" del /q "%APP_NAME%.spec"

echo [3/4] PyInstaller build (--onefile --windowed)
"%PYTHON_EXE%" -m PyInstaller --noconfirm --clean --onefile --windowed ^
 --name "%APP_NAME%" ^
 --collect-all PySide6 ^
 --collect-all qt_material ^
 --collect-all pymupdf ^
 --collect-all pypdf ^
 --collect-all numpy ^
 --collect-all cv2 ^
 --hidden-import core ^
 --hidden-import engine ^
 --hidden-import services ^
 --hidden-import controllers ^
 --hidden-import workers ^
 --hidden-import models ^
 --hidden-import config ^
 --hidden-import ui ^
 --add-data "core;core" ^
 --add-data "engine;engine" ^
 --add-data "services;services" ^
 --add-data "controllers;controllers" ^
 --add-data "workers;workers" ^
 --add-data "models;models" ^
 --add-data "config;config" ^
 --add-data "ui;ui" ^
 --add-data "prompts;prompts" ^
 main.py

echo [4/4] Verify build result
if not exist "dist\%APP_NAME%.exe" (
    echo [ERROR] EXE was not created.
    exit /b 1
)

echo Build complete!
exit /b 0
