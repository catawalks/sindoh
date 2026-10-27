@echo off
rem Build SindohBootLogo.exe (one file, no Python needed to run it).
rem Needs Python 3.8+ with Tk:  pip install pillow pyinstaller
rem The exe lands in dist\ ; build\ and the .spec file are scratch.
cd /d "%~dp0"
python -m PyInstaller --noconfirm --onefile --windowed --name SindohBootLogo ^
    --add-data "unmistakable_bootlogo.sh;." sindoh_bootlogo_gui.py
