@echo off
REM RFP pas envie de travailler : double-cliquer pour lancer. Options : run.bat --demo  /  run.bat --doctor
cd /d "%~dp0"
where py >NUL 2>NUL
if %errorlevel%==0 (py -3 run.py %*) else (python run.py %*)
if errorlevel 1 pause
