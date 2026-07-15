@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"
set "PYTHON_EXE="

for /f "delims=" %%I in ('py -c "import sys;print(sys.executable)" 2^>nul') do set "PYTHON_EXE=%%I"
if not defined PYTHON_EXE (
  for /f "delims=" %%I in ('python -c "import sys;print(sys.executable)" 2^>nul') do set "PYTHON_EXE=%%I"
)
if not defined PYTHON_EXE (
  echo [오류] 설치된 Python을 찾지 못했습니다.
  pause
  exit /b 1
)
echo %PYTHON_EXE% | findstr /I "WindowsApps" >nul
if not errorlevel 1 (
  echo [오류] Microsoft Store 실행 별칭만 감지되었습니다. 실제 Python 설치가 필요합니다.
  pause
  exit /b 1
)
"%PYTHON_EXE%" -c "import sys; assert sys.version_info >= (3,10), sys.version" >nul 2>&1
if errorlevel 1 (
  echo [오류] Python 3.10 이상이 필요합니다: %PYTHON_EXE%
  pause
  exit /b 1
)
"%PYTHON_EXE%" -c "import pymupdf" >nul 2>&1
if errorlevel 1 (
  echo [정보] 요구사항을 설치합니다.
  "%PYTHON_EXE%" -m pip install -r requirements.txt
  if errorlevel 1 (pause & exit /b 1)
)
"%PYTHON_EXE%" "%~dp0gui.py"
if errorlevel 1 pause
