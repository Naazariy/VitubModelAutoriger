@echo off
title Live2D Auto Rigger Launcher
echo Launching Live2D Auto Rigger...
cd /d "%~dp0"

if exist "venv\Scripts\python.exe" (
    venv\Scripts\python.exe auto_rigger_app.py
) else (
    python auto_rigger_app.py
)
