@echo off
chcp 65001 >nul
cd /d "%~dp0"

set "PY=%LOCALAPPDATA%\Python\bin\python.exe"
if not exist "%PY%" set "PY=python"

"%PY%" main.py
echo.
echo ---- 程序已退出：上面若有红字，就是报错信息 ----
pause
