@echo off
rem Build the exe and then the installer: dist\Pomoshnik-Buhgaltera-Setup.exe
cd /d "%~dp0"
call "%~dp0build.bat" || exit /b 1
cd /d "%~dp0"
for /f "usebackq delims=" %%v in (`.venv\Scripts\python -c "from version import __version__; print(__version__)"`) do set VER=%%v
"%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" /Q /DAppVersion=%VER% installer\setup.iss
