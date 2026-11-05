@echo off
chcp 65001 >nul
title Assistant IA local
cd /d "%~dp0"

where python >nul 2>nul || (
    echo Python introuvable. Installe-le depuis https://www.python.org et coche "Add to PATH".
    pause & exit /b 1
)
where ollama >nul 2>nul || (
    echo Ollama introuvable. Installe-le depuis https://ollama.com
    pause & exit /b 1
)

python -c "import ollama" 2>nul || (
    echo Installation du module ollama...
    python -m pip install --quiet ollama
)

rem Démarre le serveur Ollama s'il ne tourne pas déjà
tasklist /fi "imagename eq ollama.exe" | find /i "ollama.exe" >nul || start "" /min ollama serve

rem Télécharge le modèle la première fois
ollama list | find /i "llama3" >nul || ollama pull llama3

python ia.py
pause
