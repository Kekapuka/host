@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" call install.bat --quiet
echo  Jarvis в режиме браузера. Не закрывайте это окно, пока пользуетесь программой.
".venv\Scripts\python.exe" main.py --browser %*
pause
