@echo off
title DJI RC Emulator
echo Starting DJI RC Emulator...
echo.
python main.py
if errorlevel 1 (
    echo.
    echo ERROR: Failed to start. Make sure Python 3.10+ is installed.
    echo Install dependencies:  pip install -r requirements.txt
    echo.
    pause
)
