@echo off
REM Run Macro Dashboard refresh. Use this as the program in Task Scheduler.
REM Ensure working directory is project root so Python finds modules.
cd /d "%~dp0.."
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0refresh.ps1" %*
exit /b %ERRORLEVEL%
