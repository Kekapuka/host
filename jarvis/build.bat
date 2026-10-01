@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" call install.bat --quiet
".venv\Scripts\python.exe" -m pip install pyinstaller
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean jarvis.spec
if errorlevel 1 (
  echo  Сборка не удалась.
  pause
  exit /b 1
)
echo.
echo  Готово: dist\Jarvis\Jarvis.exe  (папку dist\Jarvis можно переносить целиком)
pause
