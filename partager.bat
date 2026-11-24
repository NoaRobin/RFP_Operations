@echo off
REM Prepare le zip a donner a une collegue (sans vos donnees ni vos cles). Il est pose sur le Bureau.
cd /d "%~dp0"
where py >NUL 2>NUL
if %errorlevel%==0 (py -3 run.py --partager) else (python run.py --partager)
pause
