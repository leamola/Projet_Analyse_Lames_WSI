PathologyToolbox – Analyse portable de lames IHC
PathologyToolbox est un outil portable pour analyser des lames histologiques scannées (WSI), compatible avec tout antigène IHC. Il est conçu pour être utilisé sur des postes standards Windows, sans GPU ni droits administrateurs.

🎯 Fonctionnalités

Détection et comptage automatique des cellules positives et négatives.
Calcul du pourcentage d’expression ou de perte via déconvolution DAB.
Export d’images annotées et de résultats synthétiques.

Compatible avec tout antigène IHC (CD7, CD3, etc.).
⚠️ Limitation : les fichiers DICOM (.dcm) ne sont pas optimisés pour l’instant. L’outil fonctionne pour NDPI, SVS et TIFF.

🗂 Préparation des lames

Regrouper les lames d’un patient dans un ZIP :      <PatientID>_<Antigene>.zip
Le ZIP doit contenir uniquement des fichiers NDPI ou TIFF.
L’utilisateur n’a besoin que du ZIP pour lancer l’analyse.

🛠 Prérequis

Windows 10 ou 11
Python portable 64-bit (WinPython)
 – version 3.x recommandée
Python doit être téléchargé et placé dans le dossier du dépôt comme indiqué ci-dessous.

⚙️ Installation

Télécharger Python portable depuis WinPython.
Placer le dossier Python portable dans le dépôt GitHub :

PathologyToolbox/
├─ python\WinPython64-3.x.x\
├─ setup.bat
├─ lancer_python.bat
├─ cell_detection.py
├─ annotation_global.py
├─ result.py
├─ preprocessing.py
└─ Guide_Utilisateur_Pathology_Toolbox.pdf
Important : le dossier python doit être au même niveau que setup.bat et lancer_python.bat.

Installer les dépendances automatiquement :

Double-cliquer sur setup.bat.
Le script vérifie Python et installe automatiquement les packages nécessaires (pyvips, numpy, opencv-python).
Aucune action manuelle n’est requise.

🚀 Lancer l’application

Double-cliquer sur lancer_python.bat.
Sélectionner le ZIP contenant les lames.
L’outil analysera automatiquement les lames et générera :
Images annotées des cellules détectées
Pourcentage d’expression ou de perte de l’antigène
Fichiers synthétiques pour faciliter la relecture

✅ Simple et autonome : aucun paramétrage supplémentaire n’est nécessaire.

📖 Support

Lire le guide utilisateur fourni : Guide_Utilisateur_Pathology_Toolbox.pdf
Pour questions ou contributions, utiliser le dépôt GitHub.
