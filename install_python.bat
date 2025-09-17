@echo off
REM --------------------------------------------------------
REM Install Python portable + dependencies for PathologyToolbox
REM --------------------------------------------------------

REM Vérifier si Python portable existe déjà
IF NOT EXIST "%~dp0python\WPy64-3*" (
    echo Python portable non trouvé. Veuillez placer WinPython dans tools\python\WPy64-3*
    pause
    exit /b 1
)

REM Définir le chemin vers Python portable
SET PYTHON_DIR=%~dp0python\WPy64-3*
SET PATH=%PYTHON_DIR%\;%PYTHON_DIR%\Scripts\;%PATH%

REM Vérifier la version de Python
echo Version de Python :
python --version
if ERRORLEVEL 1 (
    echo Impossible de trouver Python. Assurez-vous que WinPython est dans tools\python.
    pause
    exit /b 1
)

REM Mettre à jour pip
echo Mise à jour de pip...
python -m ensurepip --upgrade
python -m pip install --upgrade pip

REM Installer pyvips et autres dépendances nécessaires
echo Installation des packages Python...
python -m pip install pyvips numpy opencv-python

REM Vérification
echo -------------------------------
echo Vérification des installations :
python -c "import pyvips; import numpy; import cv2; print('pyvips, numpy et opencv-python installés avec succès')"
echo -------------------------------

echo Installation terminée. Python portable et packages sont prêts.
pause
