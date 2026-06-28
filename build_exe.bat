@echo off
echo ============================================
echo   Bhishmaa ERP - EXE Build Script
echo ============================================

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found! Install Python 3.11+ first.
    pause
    exit /b 1
)

echo [1/4] Installing dependencies...
pip install -r requirements.txt --quiet

echo [2/4] Installing PyInstaller...
pip install pyinstaller==6.9.0 --quiet

echo [3/4] Building EXE (this may take 5-10 minutes)...
pyinstaller bhishmaa.spec --clean --noconfirm

echo [4/4] Build complete!
if exist "dist\BhishmaaERP.exe" (
    echo.
    echo ============================================
    echo   SUCCESS! EXE created at:
    echo   dist\BhishmaaERP.exe
    echo ============================================
    echo.
    echo Copy these files to the target machine:
    echo   1. dist\BhishmaaERP.exe
    echo   2. .env  (with DATABASE_URL set)
    echo.
) else (
    echo ERROR: Build failed. Check output above.
)
pause
