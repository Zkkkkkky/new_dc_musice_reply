@echo off
setlocal
set "PROJECT_ROOT=%~dp0.."
set "PATCHER=%PROJECT_ROOT%\tools\patch_legacy_modifier_expanded_chr.py"
set "CANDIDATE=%PROJECT_ROOT%\build\legacy_modifier\SRW2_expanded_chr_candidate.exe"
set "LEGACY_DIR=%PROJECT_ROOT%\inputs\legacy_modifier"

echo EXPANDED ROM ONLY: 1 MiB PRG + 256 KiB CHR.
echo Do not use this candidate with a 512 KiB PRG ROM.
echo.

if not exist "%CANDIDATE%" (
    where python.exe >nul 2>nul
    if errorlevel 1 (
        echo python.exe was not found.
        pause
        exit /b 1
    )
    python.exe "%PATCHER%"
    if errorlevel 1 (
        echo Failed to build the candidate executable.
        pause
        exit /b 1
    )
)

pushd "%LEGACY_DIR%"
start "" "%CANDIDATE%"
popd

