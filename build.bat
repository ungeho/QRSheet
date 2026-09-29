@echo off
setlocal
cd /d "%~dp0"
rem Keep unrelated tools' ICU/OpenSSL DLLs out of PyInstaller dependency discovery.
set "PATH=%CD%\.venv\Scripts;%SystemRoot%\System32;%SystemRoot%"
if not exist .venv\Scripts\python.exe (
    echo Create .venv and install the project first. See README.md.
    exit /b 1
)
.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --windowed --onedir --name QRSheet --paths src --collect-data reportlab run.py
if errorlevel 1 exit /b 1
echo Built dist\QRSheet\QRSheet.exe
