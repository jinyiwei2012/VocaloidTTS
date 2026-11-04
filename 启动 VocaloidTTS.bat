@echo off
chcp 65001 >nul
cd /d "%~dp0"
if exist "VocaloidTTS.exe" (
  start "" "VocaloidTTS.exe"
) else (
  python VocaloidTTS.py
)
