@echo off
chcp 65001 >nul
title Black Jack - Apercu
cd /d "%~dp0"

rem ============================================================
rem  APERCU : montre tout le visuel de Black Jack (intro, logo,
rem  menu, commandes systeme). N'exige RIEN a installer.
rem  Le chat de l'IA ne repond que si Ollama tourne ; la
rem  recherche web marche en plus si le module ddgs est installe
rem  (python -m pip install ddgs), mais ce n'est pas obligatoire.
rem
rem  >>> Ouvre de preference TERMINAL WINDOWS pour les couleurs.
rem      Si Windows bloque ce .bat, lance a la place :  python ia.py
rem ============================================================

where python >nul 2>nul || (
    echo Python introuvable. Installe-le depuis https://www.python.org
    echo IMPORTANT : pendant l'installation, coche "Add python.exe to PATH".
    pause & exit /b 1
)

cls
python ia.py
if errorlevel 1 pause
