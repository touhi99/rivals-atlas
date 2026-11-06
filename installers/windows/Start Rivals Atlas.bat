@echo off
rem Rivals Atlas: install what is missing on the first run, then open the dashboard.
setlocal EnableExtensions
title Rivals Atlas

set "WHEEL="
for /f "delims=" %%f in ('dir /b "%~dp0rivals_atlas-*.whl" 2^>nul') do set "WHEEL=%~dp0%%f"

set "APPDIR=%LOCALAPPDATA%\Rivals Atlas"
if not exist "%APPDIR%" mkdir "%APPDIR%" >nul 2>&1
cd /d "%APPDIR%"

set "PATH=%USERPROFILE%\.local\bin;%PATH%"
where uv >nul 2>&1
if not errorlevel 1 goto run

echo Installing Rivals Atlas for the first time. This takes a minute or two...
powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
if errorlevel 1 goto failed
set "PATH=%USERPROFILE%\.local\bin;%PATH%"

:run
rem Prefer the published package (it keeps itself current); fall back to the wheel in this folder.
set "FROM=rivals-atlas"
uvx --from rivals-atlas rivals-atlas --help >nul 2>nul
if not errorlevel 1 goto launch
if not defined WHEEL goto nowheel
set "FROM=%WHEEL%"

:launch
echo Starting Rivals Atlas. Close this window to stop it.
uvx --from "%FROM%" rivals-atlas serve --open
if errorlevel 1 goto failed
exit /b 0

:nowheel
echo Rivals Atlas is not published yet and this folder has no wheel.
echo Download the release zip again and keep the files together.
pause
exit /b 1

:failed
echo.
echo Rivals Atlas could not start. The message above says why.
pause
exit /b 1
