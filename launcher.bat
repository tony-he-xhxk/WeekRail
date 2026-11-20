@echo off
rem Single-window design:
rem  Outer stage: relaunch THIS bat inside classic conhost, then quit immediately
rem  so the empty cmd window closes. Result: only ONE window.
rem  Extra args (e.g. --auto) are forwarded to launcher.py.
if "%1"=="_inner_" goto :inner

cd /d "%~dp0"
start "" conhost.exe cmd /c "%~f0" _inner_ %*
exit /b

:inner
cd /d "%~dp0"
set "PYEXE="
for %%P in (python.exe) do if not defined PYEXE set "PYEXE=%%~$PATH:P"
if not defined PYEXE if exist "%LOCALAPPDATA%\Programs\Python\Python310\python.exe" set "PYEXE=%LOCALAPPDATA%\Programs\Python\Python310\python.exe"
if not defined PYEXE if exist "%ProgramFiles%\Python310\python.exe" set "PYEXE=%ProgramFiles%\Python310\python.exe"
if not defined PYEXE if exist "%ProgramFiles%\Python311\python.exe" set "PYEXE=%ProgramFiles%\Python311\python.exe"
if not defined PYEXE (
  echo [ERR] Python 3 not found. Install Python 3.10+ and add it to PATH.
  pause
  exit /b 1
)
"%PYEXE%" launcher.py %2
if errorlevel 1 pause
