#!/bin/bash
echo "============================================"
echo "  Bhishmaa ERP - EXE Build Script (Linux)"
echo "============================================"

echo "[1/4] Installing dependencies..."
pip install -r requirements.txt -q

echo "[2/4] Installing PyInstaller..."
pip install pyinstaller==6.9.0 -q

echo "[3/4] Building binary..."
pyinstaller bhishmaa.spec --clean --noconfirm

echo "[4/4] Done!"
if [ -f "dist/BhishmaaERP" ]; then
    echo "SUCCESS: dist/BhishmaaERP created"
else
    echo "ERROR: Build failed"
fi
