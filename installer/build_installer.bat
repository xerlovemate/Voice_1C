@echo off
setlocal enabledelayedexpansion

cd /d "%~dp0\.."

set VENV=.venv_build
set PYTHON=python
set ISCC=

if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not "%INNO_ISCC%"=="" set "ISCC=%INNO_ISCC%"

if not exist "%VENV%\Scripts\python.exe" (
  echo [build] Creating build venv...
  %PYTHON% -m venv "%VENV%"
  if errorlevel 1 exit /b 1
)

echo [build] Installing dependencies...
"%VENV%\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 exit /b 1
"%VENV%\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 exit /b 1

echo [build] Cleaning previous artifacts...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist dist_installer rmdir /s /q dist_installer
mkdir dist_installer

echo [build] Building Voice1C.exe...
"%VENV%\Scripts\pyinstaller.exe" --clean --noconfirm Voice1C.spec
if errorlevel 1 exit /b 1

if "%ISCC%"=="" (
  echo [error] Inno Setup compiler ISCC.exe not found.
  echo [error] Install Inno Setup 6 from https://jrsoftware.org/isdl.php
  echo [error] Expected path: "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
  echo [error] Or set INNO_ISCC to full path of ISCC.exe and run build_release.bat again.
  exit /b 2
)

echo [build] Building installer...
"%ISCC%" installer\Voice1C.iss
if errorlevel 1 exit /b 1

echo [build] Done: dist_installer\Voice1CSetup.exe
exit /b 0
