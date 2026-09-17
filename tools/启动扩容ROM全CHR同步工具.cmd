@echo off
setlocal
set "CHR_SYNC=%~dp0..\src\chr_sync\app.pyw"
where pythonw.exe >nul 2>nul
if errorlevel 1 (
    echo pythonw.exe was not found. Install Python 3.10 or newer with Tkinter.
    pause
    exit /b 1
)
start "" pythonw.exe "%CHR_SYNC%" %*

