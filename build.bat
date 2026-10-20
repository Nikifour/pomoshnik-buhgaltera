@echo off
rem Local build of the exe (releases are built by GitHub Actions)
cd /d "%~dp0"
.venv\Scripts\python -m PyInstaller --noconfirm --clean --onefile --windowed --name "Pomoshnik-Buhgaltera" --icon assets\icon.ico --add-data "assets;assets" --exclude-module tkinter app.py
