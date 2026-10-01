@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" call install.bat --quiet
if not exist ".venv\Scripts\pythonw.exe" exit /b 1
start "" ".venv\Scripts\pythonw.exe" main.py %*
