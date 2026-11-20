@echo off
rem UniSchedule one-click start (also fine as a Windows Startup shortcut).
rem  Same as launcher.bat --auto: opens the schedule bar for TODAY,
rem  so no "3" + Enter + Enter typing is needed.
rem  Single-window conhost design and the tray icon are unchanged.
rem  The console window is minimized automatically once the bar is up.
cd /d "%~dp0"
call "%~dp0launcher.bat" --auto
exit /b
