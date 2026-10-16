# -*- mode: python ; coding: utf-8 -*-
# Build with:  npm run build:backend   (from the app/ folder)
import sys
from PyInstaller.utils.hooks import collect_data_files

# Ship only the Stockfish build for the OS we are building on.
if sys.platform.startswith('win'):
    stockfish = 'stockfish/stockfish-windows-x86-64.exe'
else:
    stockfish = 'stockfish/stockfish-ubuntu-x86-64'

a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=[(stockfish, 'stockfish')],
    # SpeechRecognition ships the `flac` converter it needs for Google recognition as package data.
    datas=collect_data_files('speech_recognition'),
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['scipy', 'nltk', 'numpy', 'tkinter', 'pyttsx3'],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='chess_backend',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name='chess_backend',
)
