@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"

set "PYTHON_EXE="

:: 1. py 런처로 최신 파이썬 3.x 확인
for /f "delims=" %%I in ('py -3 -c "import sys; print(sys.executable)" 2^>nul') do (
    echo %%I | findstr /i "WindowsApps" >nul
    if errorlevel 1 set "PYTHON_EXE=%%I"
)

:: 2. 기본 python 명령 확인
if not defined PYTHON_EXE (
    for /f "delims=" %%I in ('python -c "import sys; print(sys.executable)" 2^>nul') do (
        echo %%I | findstr /i "WindowsApps" >nul
        if errorlevel 1 set "PYTHON_EXE=%%I"
    )
)

:: 3. AppData 파이썬 경로 순회 (버전 무관)
if not defined PYTHON_EXE (
    for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do (
        if exist "%%D\python.exe" set "PYTHON_EXE=%%D\python.exe"
    )
)

:: 4. C:\ 드라이브 파이썬 경로 순회
if not defined PYTHON_EXE (
    for /d %%D in ("C:\Python3*") do (
        if exist "%%D\python.exe" set "PYTHON_EXE=%%D\python.exe"
    )
)

if not defined PYTHON_EXE (
    echo [오류] 실제 Python 인터프리터를 찾지 못했습니다.
    pause
    exit /b 1
)

echo 사용 Python: %PYTHON_EXE%
"%PYTHON_EXE%" -c "import pymupdf, customtkinter" >nul 2>&1
if errorlevel 1 (
    echo 필요한 패키지를 먼저 설치합니다...
    "%PYTHON_EXE%" -m pip install -r requirements.txt
    if errorlevel 1 pause & exit /b 1
)

"%PYTHON_EXE%" "%~dp0gui.py"
if errorlevel 1 pause
