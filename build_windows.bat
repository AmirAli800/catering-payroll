@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if errorlevel 1 (
  echo Python was not found. Install Python 3.11 or newer first.
  exit /b 1
)

python -m pip install -r requirements-build.txt
if errorlevel 1 exit /b 1

python -m PyInstaller --noconfirm --clean --onefile --windowed --name CateringPayroll app.py
if errorlevel 1 exit /b 1

where ISCC >nul 2>nul
if errorlevel 1 (
  echo.
  echo Portable app created: dist\CateringPayroll.exe
  echo To create the installer, install Inno Setup 6 and run:
  echo ISCC installer.iss
  exit /b 0
)

ISCC installer.iss
if errorlevel 1 exit /b 1

echo.
echo Installer created in the output folder.
endlocal
