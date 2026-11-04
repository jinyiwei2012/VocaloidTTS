@echo off
chcp 65001 >nul
set "DEST=%ProgramFiles(x86)%\Vocaloid4FE\JobPlugins"
if not exist "%DEST%" (
  echo VOCALOID4 JobPlugins folder not found:
  echo %DEST%
  pause
  exit /b 1
)
copy /Y "%~dp0jobplugin\VocaloidTTS.lua" "%DEST%\VocaloidTTS.lua"
if errorlevel 1 (
  echo Copy failed. Run this script as administrator.
) else (
  echo Copied to: %DEST%\VocaloidTTS.lua
  echo In V4: Job - Manage Job Plugins - Add - select this file.
)
pause
