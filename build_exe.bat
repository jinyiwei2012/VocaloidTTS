@echo off
chcp 65001 >nul
cd /d "%~dp0"
python -m pip install -r requirements.txt pyinstaller
pyinstaller --noconfirm --clean --onedir ^
  --name VocaloidTTS ^
  --icon "assets\vocaloidtts.ico" ^
  --add-data "jobplugin;jobplugin" ^
  --add-data "assets;assets" ^
  --collect-all pypinyin ^
  VocaloidTTS.py
if exist "dist\VocaloidTTS\VocaloidTTS.exe" (
  echo.
  echo Build OK: dist\VocaloidTTS\VocaloidTTS.exe
) else (
  echo Build FAILED, check the log above.
)
pause
