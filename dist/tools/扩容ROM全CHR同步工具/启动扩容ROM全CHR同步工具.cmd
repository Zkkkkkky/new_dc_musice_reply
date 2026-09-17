@echo off
setlocal
where pythonw.exe >nul 2>nul
if errorlevel 1 (
    echo pythonw.exe was not found. Install Python 3.10 or newer with Tkinter.
    pause
    exit /b 1
)
start "" pythonw.exe "%~dp0expanded_chr_sync.pyw" %*
