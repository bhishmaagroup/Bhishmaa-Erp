@echo off
title Bhishmaa ERP

echo Starting Bhishmaa ERP Server...
timeout /t 1 >nul

REM Auto open browser
start "" http://127.0.0.1:5000

REM Start Flask server
python app.py