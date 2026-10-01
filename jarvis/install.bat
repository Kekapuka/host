@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo.
echo  === Jarvis: установка ===
echo.

set "PY="
for %%V in (3.13 3.12 3.11 3.14) do (
  if not defined PY (
    py -%%V -c "import sys" >nul 2>nul && set "PY=py -%%V"
  )
)
if not defined PY (
  python -c "import sys; assert sys.version_info >= (3, 10)" >nul 2>nul && set "PY=python"
)
if not defined PY (
  echo  Python не найден.
  echo  Установите Python 3.12 или 3.13 с https://www.python.org/downloads/
  echo  и при установке отметьте "Add python.exe to PATH".
  pause
  exit /b 1
)

echo  Python: %PY%
if not exist ".venv\Scripts\python.exe" (
  %PY% -m venv .venv
  if errorlevel 1 (
    echo  Не удалось создать виртуальное окружение.
    pause
    exit /b 1
  )
)

".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
  echo.
  echo  Ошибка установки зависимостей. Проверьте интернет и попробуйте ещё раз.
  pause
  exit /b 1
)

echo.
echo  Готово! Запускайте start.bat
echo.
if /i not "%~1"=="--quiet" pause
