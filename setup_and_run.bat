@echo off
title DJI RC Emulator — Setup & Run
color 0B
echo.
echo  ============================================
echo    DJI RC Emulator — First-Time Setup
echo  ============================================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    color 0C
    echo  [ERROR] Python is not installed or not in PATH!
    echo.
    echo  Please install Python 3.10+ from:
    echo    https://www.python.org/downloads/
    echo.
    echo  IMPORTANT: Check "Add Python to PATH" during install!
    echo.
    pause
    exit /b 1
)

:: Show python version
echo  [OK] Python found:
python --version
echo.

:: Install pip dependencies
echo  Installing required Python packages...
echo  ----------------------------------------
pip install --quiet --upgrade pip >nul 2>&1
pip install -r requirements.txt
if errorlevel 1 (
    color 0E
    echo.
    echo  [WARNING] Some packages may have failed to install.
    echo  The app will still try to start.
    echo.
)
echo.
echo  [OK] Dependencies installed!
echo.

:: Check ViGEm
echo  Checking ViGEm Bus Driver...
python -c "import vgamepad; vgamepad.VX360Gamepad()" >nul 2>&1
if errorlevel 1 (
    color 0E
    echo  [WARNING] ViGEm Bus Driver not detected!
    echo.
    echo  You need to install it for the virtual gamepad to work:
    echo    https://github.com/nefarius/ViGEmBus/releases
    echo.
    echo  Download and run: ViGEmBus_Setup_x64.msi
    echo  Then reboot your PC.
    echo.
    echo  The app will start but gamepad emulation won't work
    echo  until ViGEm is installed.
    echo.
    pause
) else (
    echo  [OK] ViGEm is installed!
)

echo.
echo  ============================================
echo    Starting DJI RC Emulator...
echo  ============================================
echo.
python main.py
if errorlevel 1 (
    echo.
    echo  [ERROR] App crashed. Check the error above.
    pause
)
