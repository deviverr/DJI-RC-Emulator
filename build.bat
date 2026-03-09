@echo off
title DJI RC Emulator — PyInstaller Build
echo ============================================
echo   DJI RC Emulator — Build Script
echo ============================================
echo.

:: Activate venv if present
if exist ".venv\Scripts\activate.bat" (
    echo Activating virtual environment...
    call .venv\Scripts\activate.bat
)

:: Check PyInstaller is installed
pyinstaller --version >nul 2>&1
if errorlevel 1 (
    echo PyInstaller not found. Installing...
    pip install pyinstaller>=6.0
    if errorlevel 1 (
        echo Failed to install PyInstaller.
        pause
        exit /b 1
    )
)

echo.
echo Running PyInstaller...
echo.

pyinstaller DJI_RC_Emulator.spec --noconfirm

if errorlevel 1 (
    echo.
    echo ============================================
    echo   BUILD FAILED — Check output above
    echo ============================================
    pause
    exit /b 1
)

echo.
echo ============================================
echo   BUILD COMPLETE
echo   Output: dist\DJI_RC_Emulator\DJI_RC_Emulator.exe
echo ============================================
echo.
pause
