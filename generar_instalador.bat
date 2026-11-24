@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo.
echo  Generando el instalador de SimuladorConan ...
echo  (Normalmente no hace falta: GitHub lo genera solo al publicar una version.)
echo.

python --version >nul 2>&1 || (echo  No encuentro Python. Instala Python 3.12 y marca "Add python.exe to PATH". & goto :error)
if exist SimuladorConan\app.py (echo  Hay una copia del proyecto dentro de esta carpeta ^(SimuladorConan\SimuladorConan^). Borrala. & goto :error)

for /f "delims=" %%V in ('python -c "from core.version import VERSION; print(VERSION)"') do set VERSION=%%V
echo  Version: %VERSION%

python -m pip install --upgrade -r requirements.txt || goto :error
for /d /r %%D in (__pycache__) do @if exist "%%D" rd /s /q "%%D"
set QT_QPA_PLATFORM=offscreen
python -m pytest tests -q || (echo. & echo  Las pruebas han fallado: no genero el instalador. & goto :error)
set QT_QPA_PLATFORM=

python -m PyInstaller --noconfirm --clean SimuladorConan.spec || goto :error

set ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe
if not exist "%ISCC%" set ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe
if not exist "%ISCC%" (
  echo.
  echo  El programa ya esta en dist\SimuladorConan, pero para crear el instalador
  echo  falta Inno Setup 6: https://jrsoftware.org/isdl.php
  goto :error
)
"%ISCC%" /DVersion=%VERSION% instalador\SimuladorConan.iss || goto :error

echo.
echo  Listo: salida\SimuladorConan-Setup-%VERSION%.exe
explorer salida
pause
exit /b 0

:error
echo.
echo  Ha habido un error. Copia lo que sale arriba y pasamelo.
pause
exit /b 1
