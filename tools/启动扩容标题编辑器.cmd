@echo off
setlocal
set "TITLE_EDITOR=%~dp0..\src\title_editor\app.pyw"
where pythonw.exe >nul 2>nul
if errorlevel 1 (
    echo 未找到 pythonw.exe，请先安装带 Tkinter 的 Python 3.10 或更高版本。
    pause
    exit /b 1
)
start "" pythonw.exe "%TITLE_EDITOR%" %*

