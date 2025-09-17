PathologyToolbox – Installation et utilisation

Introduction
PathologyToolbox est un outil portable pour l’analyse de lames histologiques scannées (WSI), utilisable pour n’importe quel antigène IHC.

L’outil permet de :
--> Compter automatiquement les cellules positives et négatives pour un antigène donné.
--> Calculer le pourcentage d’expression ou de perte via déconvolution DAB.
--> Produire des images annotées et indicateurs synthétiques pour faciliter la relecture clinique.

Il fonctionne sur des postes standards, sans GPU ni droits administrateurs, et repose sur des logiciels open source (Python portable).
⚠️ Limitation actuelle : l’outil n’est pas optimisé pour les fichiers DICOM (.dcm). Il est prévu pour être amélioré sur ce point dans les versions futures.

Préparation des lames
  Les lames doivent être fournies en format NDPI,TIFF ou SVS.
  Chaque patient doit avoir ses lames regroupées dans un fichier ZIP nommé comme suit :

<PatientID>_<Antigene>.zip

Après cette préparation, l’utilisateur n’a besoin que du ZIP pour lancer l’analyse.

Prérequis

Windows 10 ou 11
setup.bat fourni avec l’outil
Dossier Python portable WinPython placé dans :

tools\python\WPy64-3*

Structure des fichiers
PathologyToolbox/
├─ setup.bat
├─ python/                  <- WinPython portable
├─ annotation_global.py
├─ cell_detection.py
├─ Guide_Utilisateur_Pathology_Toolbox.pdf
└─ ...

Installation

Double-cliquer sur setup.bat.

Vérifie la présence de Python portable

Met à jour pip

Installe les dépendances : pyvips, numpy, opencv-python

Fin de l’installation :

Installation terminée. Python portable et packages sont prêts.

Vérification
python -c "import pyvips; import numpy; import cv2; print('pyvips, numpy et opencv-python installés avec succès')"

Utilisation

Lancer l’analyse sur le ZIP contenant les lames :

python cell_detection.py --input <PatientID_Antigene.zip>


Fonctionnalités :

Détection et comptage automatique des cellules positives et négatives.
Calcul du pourcentage d’expression ou de perte via déconvolution DAB.
Export d’images annotées et de résultats synthétiques.
Compatible avec tout antigène IHC (CD7, CD3, etc.).
✅ Simple : l’utilisateur fournit juste le ZIP préparé.

Support

Consulter le guide utilisateur fourni :
Guide_Utilisateur_Pathology_Toolbox.pdf
Pour toute question ou retour, le dépôt GitHub est disponible pour suivi et contributions.
