@echo off
setlocal

set "ROOT=%~dp0"
set "PYDIR=%ROOT%tools\python\WPy64-31241\python-3.12.4.amd64"
set "SCRIPTS=%ROOT%tools\python\WPy64-31241\Scripts"

rem Utilise les binaires embarqués (pyvips-binary / openslide-bin)
set "PYVIPS_USE_BINARY=1"

rem Ajoute Python portable au PATH
set "PATH=%SCRIPTS%;%PYDIR%;%PATH%"

rem ----- MODE NORMAL (sans console) -----
start "" "%PYDIR%\pythonw.exe" "%ROOT%mainGUI.py"
exit /b
