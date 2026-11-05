@echo off
REM Collecte "Qui contacter" : double-cliquer. Installe ce qu'il faut la premiere fois (Python et 2 bibliotheques,
REM dans le profil de l'utilisateur, sans droits administrateur), puis lit Outlook et depose l'Excel sur SharePoint.
setlocal EnableExtensions
chcp 65001 >nul
title Collecte Qui contacter - equipe RFP
cd /d "%~dp0"
set "BASE=%LOCALAPPDATA%\RFPCollecte"
set "VENV=%BASE%\venv"
set "VPY=%VENV%\Scripts\python.exe"
set "PS=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
set "PYVER=3.12.10"

if exist "%VPY%" goto deps

echo.
echo   Premiere utilisation : installation (quelques minutes, une seule fois).
set "PY="
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul && set "PY=py -3"
if not defined PY python -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul && set "PY=python"
if not defined PY if exist "%BASE%\Python312\python.exe" set PY="%BASE%\Python312\python.exe"
if defined PY goto venv

echo   Python n'est pas installe : telechargement depuis python.org (version %PYVER%, pour vous seul)...
if not exist "%BASE%" mkdir "%BASE%"
"%PS%" -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; [Net.ServicePointManager]::SecurityProtocol='Tls12'; [Net.WebRequest]::DefaultWebProxy.Credentials=[Net.CredentialCache]::DefaultNetworkCredentials; Invoke-WebRequest -UseBasicParsing -Uri 'https://www.python.org/ftp/python/%PYVER%/python-%PYVER%-amd64.exe' -OutFile '%BASE%\python-installer.exe'"
if errorlevel 1 goto nopython
"%BASE%\python-installer.exe" /quiet InstallAllUsers=0 Include_launcher=0 PrependPath=0 Include_test=0 Shortcuts=0 TargetDir="%BASE%\Python312"
if not exist "%BASE%\Python312\python.exe" goto nopython
del "%BASE%\python-installer.exe" >nul 2>nul
set PY="%BASE%\Python312\python.exe"

:venv
echo   Preparation de l'environnement...
%PY% -m venv "%VENV%"
if not exist "%VPY%" goto failed

:deps
"%VPY%" -c "import win32com.client, openpyxl" >nul 2>nul
if not errorlevel 1 goto run
echo   Installation des bibliotheques (pywin32, openpyxl)...
"%VPY%" -m pip install --disable-pip-version-check -q pywin32 openpyxl
if errorlevel 1 goto nopip

:run
echo.
"%VPY%" "%~dp0collecte.py" %*
echo.
pause
exit /b 0

:nopython
echo.
echo   Impossible d'installer Python automatiquement (python.org bloque par le proxy ?).
echo   Installez "Python 3.12" depuis le Portail d'entreprise / Software Center, puis relancez ce fichier.
pause
exit /b 1

:nopip
echo.
echo   Impossible d'installer les bibliotheques (pypi.org bloque par le proxy ?).
echo   Demandez a l'IT l'acces a pypi.org, ou faites installer pywin32 et openpyxl, puis relancez.
pause
exit /b 1

:failed
echo.
echo   Echec de la preparation de l'environnement Python : envoyez une capture de cette fenetre.
pause
exit /b 1
