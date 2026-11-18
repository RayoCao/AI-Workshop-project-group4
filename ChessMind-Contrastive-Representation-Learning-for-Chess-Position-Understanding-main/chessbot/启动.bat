@echo off
chcp 65001 >nul
cd /d "%~dp0"

set "PYW=%LOCALAPPDATA%\Python\bin\pythonw.exe"
if exist "%PYW%" (
    start "" "%PYW%" main.py
    goto :eof
)

where py >nul 2>nul
if not errorlevel 1 (
    start "" py -3w main.py
    goto :eof
)

echo [错误] 没找到带 tkinter 的 Python。
echo 请把本文件里的 PYW 改成你自己的 pythonw.exe 完整路径。
pause
