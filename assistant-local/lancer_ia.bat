@echo off
chcp 65001 >nul
title Assistant IA local - Mon-IA
cd /d "%~dp0"

set "BASE=llama3.1:8b-instruct-q4_K_M"

where python >nul 2>nul || (
    echo Python introuvable. Installe-le depuis https://www.python.org et coche "Add to PATH".
    pause & exit /b 1
)
where ollama >nul 2>nul || (
    echo Ollama introuvable. Installe-le depuis https://ollama.com
    pause & exit /b 1
)

python -c "import ollama, ddgs" 2>nul || (
    echo Installation des modules Python ^(ollama, ddgs^)...
    python -m pip install --quiet ollama ddgs
)

rem ===== Optimisations RTX 4060 (8 Go) + Ryzen 5 5600 =====
rem Flash attention : plus rapide et moins de mémoire GPU
set OLLAMA_FLASH_ATTENTION=1
rem Cache de contexte en 8 bits : moitié moins de VRAM, perte de qualité négligeable
set OLLAMA_KV_CACHE_TYPE=q8_0
rem Un seul modèle et une seule requête à la fois : toute la VRAM pour Mon-IA
set OLLAMA_MAX_LOADED_MODELS=1
set OLLAMA_NUM_PARALLEL=1
rem Garde le modèle chargé 30 min (pas de rechargement entre deux questions)
set OLLAMA_KEEP_ALIVE=30m

rem Redémarre Ollama pour qu'il prenne ces réglages
rem (l'appli Ollama de la barre des tâches tourne sinon avec ses réglages par défaut)
taskkill /f /im "ollama app.exe" >nul 2>nul
taskkill /f /im ollama.exe >nul 2>nul
timeout /t 1 /nobreak >nul
start "Ollama" /min ollama serve

echo Démarrage d'Ollama...
:attente
timeout /t 1 /nobreak >nul
ollama list >nul 2>nul || goto attente

rem Télécharge la base la première fois (environ 4,9 Go)
ollama list | find /i "%BASE%" >nul || ollama pull %BASE%

rem Crée (ou met à jour) ton modèle à partir du Modelfile
echo Création du modèle mon-ia...
ollama create mon-ia -f Modelfile >nul || (echo Échec de la création du modèle. & pause & exit /b 1)

python ia.py
pause
