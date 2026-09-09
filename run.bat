@echo off
title Live2D Geometry Deformation Prototype Launcher
echo =======================================================
echo   Live2D Geometry Deformation Prototype (Keyframe-Free)
echo =======================================================
echo Launching application...
cd /d "%~dp0"

if exist "venv\Scripts\python.exe" (
    venv\Scripts\python.exe main.py
) else (
    python main.py
)

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Application exited with code %ERRORLEVEL%.
    pause
)
