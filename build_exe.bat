@echo off
chcp 65001 >nul
cd /d "%~dp0"

rem Stop at the first failure. Without these checks the script fell through to
rem the "does the exe exist" test below, so a failed pip install or a missing
rem PyInstaller still printed "Build OK" as long as dist held an older build.
python -m pip install -r requirements.txt pyinstaller
if errorlevel 1 goto failed

pyinstaller --noconfirm --clean --onedir ^
  --name VocaloidTTS ^
  --icon "assets\vocaloidtts.ico" ^
  --add-data "jobplugin;jobplugin" ^
  --add-data "assets;assets" ^
  --collect-all pypinyin ^
  VocaloidTTS.py
if errorlevel 1 goto failed

rem PyInstaller reported success, so an exe at this path is this build's output.
if not exist "dist\VocaloidTTS\VocaloidTTS.exe" goto failed

echo.
echo Build OK: dist\VocaloidTTS\VocaloidTTS.exe
pause
exit /b 0

:failed
echo.
echo Build FAILED, check the log above.
pause
exit /b 1
