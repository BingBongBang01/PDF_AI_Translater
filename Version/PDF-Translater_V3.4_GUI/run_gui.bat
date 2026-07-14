@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
set "PYTHON_EXE="
for /f "usebackq delims=" %%I in (`py -3.12 -c "import sys; print(sys.executable)" 2^>nul`) do set "PYTHON_EXE=%%I"
if not defined PYTHON_EXE (
 echo Python 3.12를 찾지 못했습니다.
 py -0p
 pause
 exit /b 1
)
echo 사용 Python: %PYTHON_EXE%
"%PYTHON_EXE%" gui.py
if errorlevel 1 pause
