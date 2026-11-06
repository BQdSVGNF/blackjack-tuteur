@echo off
chcp 65001 >nul
title Black Jack - Apercu
cd /d "%~dp0"

rem ============================================================
rem  APERCU : montre tout le visuel de Black Jack (intro, logo,
rem  menu, recherche web, commandes systeme) SANS installer
rem  Ollama ni le modele. Le chat de l'IA, lui, repondra seulement
rem  si Ollama tourne (voir lancer_ia.bat pour la version complete).
rem
rem  >>> Ouvre ce fichier dans TERMINAL WINDOWS pour les belles
rem      couleurs. Dans le vieux cmd noir, le logo sera moche.
rem ============================================================

where python >nul 2>nul || (
    echo Python introuvable. Installe-le depuis https://www.python.org
    echo IMPORTANT : pendant l'installation, coche "Add python.exe to PATH".
    pause & exit /b 1
)

python -c "import ollama, ddgs" 2>nul || (
    echo Installation des petits modules Python ^(une seule fois^)...
    python -m pip install --quiet ollama ddgs
)

cls
python ia.py
if errorlevel 1 pause
