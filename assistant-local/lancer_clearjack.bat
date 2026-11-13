@echo off
chcp 65001 >nul
title ClearJack
cd /d "%~dp0"
where python >nul 2>nul || (
    echo Python introuvable. Installe-le depuis https://www.python.org et coche "Add to PATH".
    pause & exit /b 1
)
cls
python clearjack.py
if errorlevel 1 pause
