@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul
cd /d "%~dp0"

echo =======================================================
echo PDF AI Translater - Setup.exe Builder (Inno Setup)
echo =======================================================
echo.

echo [1/6] Locate base Python interpreter...
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
    echo [ERROR] Could not locate a valid Python interpreter.
    goto :error
)
echo Using Base Python: %BASE_PYTHON%

echo.
echo [2/6] Locate Inno Setup compiler (ISCC.exe)...
set "ISCC="
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not defined ISCC for /f "delims=" %%I in ('where ISCC.exe 2^>nul') do set "ISCC=%%I"

if not defined ISCC (
    echo Inno Setup not found. Installing via winget...
    winget install -e --id JRSoftware.InnoSetup --source winget ^
        --accept-source-agreements --accept-package-agreements --silent
    if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
    if not defined ISCC if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
)
if not defined ISCC (
    echo [ERROR] Inno Setup 6 is required. Install it from https://jrsoftware.org/isdl.php
    goto :error
)
echo Using ISCC: %ISCC%

echo.
echo [3/6] Read app version...
set "APP_VERSION="
for /f "usebackq delims=" %%V in (`"%BASE_PYTHON%" "..\_get_version.py" 2^>nul`) do set "APP_VERSION=%%V"
if not defined APP_VERSION (
    echo [ERROR] Could not read __version__ from ..\_get_version.py
    goto :error
)
set "APP_EXE=..\dist\PDF-Translater-v%APP_VERSION%.exe"
echo App version: %APP_VERSION%

echo.
echo [4/6] Ensure the application EXE is built...
if not exist "%APP_EXE%" (
    echo   "%APP_EXE%" not found - running ..\build_exe.bat
    pushd ".."
    call build_exe.bat
    set "BUILD_RC=!errorlevel!"
    popd
    if not "!BUILD_RC!"=="0" (
        echo [ERROR] build_exe.bat failed with code !BUILD_RC!
        goto :error
    )
)
if not exist "%APP_EXE%" (
    echo [ERROR] Application EXE still missing: %APP_EXE%
    goto :error
)
for %%F in ("%APP_EXE%") do echo   Found: %%~nxF (%%~zF bytes)

echo.
echo [5/6] Compute SHA-256 of the application EXE...
REM The web installer pins this hash so a tampered or truncated download is rejected.
set "APPEXE_SHA256="
for /f "skip=1 delims=" %%H in ('certutil -hashfile "%APP_EXE%" SHA256') do (
    if not defined APPEXE_SHA256 set "APPEXE_SHA256=%%H"
)
REM Older certutil builds group the hash in space-separated pairs - strip them.
set "APPEXE_SHA256=%APPEXE_SHA256: =%"
echo %APPEXE_SHA256% | findstr /r "^[0-9a-fA-F][0-9a-fA-F]*$" >nul
if errorlevel 1 (
    echo [ERROR] Unexpected certutil output; got "%APPEXE_SHA256%"
    goto :error
)
echo   SHA-256: %APPEXE_SHA256%

echo.
echo [6/6] Compile installers...
REM Warn (do not block) when download integrity checks are still disabled.
set "UNPINNED="
for /f "usebackq delims=" %%E in (`"%BASE_PYTHON%" "tools\update_checksums.py" --list-empty 2^>nul`) do set "UNPINNED=%%E"
if defined UNPINNED (
    echo.
    echo   [WARNING] Download integrity checking is OFF for: !UNPINNED!
    echo   [WARNING] Run "python tools\update_checksums.py" on a networked PC to pin them.
    echo.
)
if not exist "Output" mkdir "Output"

echo   -^> web installer
"%ISCC%" /Q "/DAppVersion=%APP_VERSION%" "/DAppExeSha256=%APPEXE_SHA256%" setup.iss
if errorlevel 1 goto :error

REM The offline variant is only built when the redistributables have been staged.
REM Fetch them first (on a networked machine):
REM   curl -L -o redist\vc_redist.x64.exe https://aka.ms/vs/17/release/vc_redist.x64.exe
REM   curl -L -O --output-dir redist https://digi.bib.uni-mannheim.de/tesseract/tesseract-ocr-w64-setup-<ver>.exe
REM The offline variant embeds both redistributables via Flags: dontcopy, so both
REM must be present at compile time or ISCC fails on a missing [Files] source.
set "TESS_SETUP="
for %%F in ("redist\tesseract-ocr-w64-setup-*.exe") do set "TESS_SETUP=%%~nxF"
if not exist "redist\vc_redist.x64.exe" (
    echo   -^> offline installer SKIPPED ^(redist\vc_redist.x64.exe not staged^)
) else if not defined TESS_SETUP (
    echo   -^> offline installer SKIPPED ^(redist\tesseract-ocr-w64-setup-*.exe not staged^)
) else (
    echo   -^> offline installer ^(bundling !TESS_SETUP!^)
    "%ISCC%" /Q /DOFFLINE "/DAppVersion=%APP_VERSION%" "/DAppExeSha256=%APPEXE_SHA256%" setup.iss
    if errorlevel 1 goto :error
)

echo.
echo =======================================================
echo Build SUCCESS!
dir /b "Output\*.exe"
echo =======================================================
pause
exit /b 0

:error
echo.
echo [ERROR] Setup build failed. Please check the log above.
pause
exit /b 1
