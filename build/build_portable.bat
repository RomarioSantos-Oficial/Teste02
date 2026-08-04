@echo off
REM =============================================================
REM   Build Portavel - SectorFlow ALFA
REM   Gera uma pasta pronta para copiar e executar em qualquer PC
REM =============================================================

echo.
echo ========================================
echo   SectorFlow ALFA - Build Portavel
echo ========================================
echo.

REM Verificar Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERRO] Python nao encontrado. Instale Python 3.10+
    pause
    exit /b 1
)

REM Instalar dependencias
echo [1/3] Verificando/Instalando dependencias...
pip install PySide6 pyinstaller --quiet

REM Limpar build anterior
echo [2/3] Limpando build anterior...
if exist "build\SectorFlow" rmdir /s /q build\SectorFlow
if exist "dist\SectorFlow" rmdir /s /q dist\SectorFlow

REM Executar PyInstaller
echo [3/3] Gerando executavel...
pyinstaller --clean --noconfirm build\SectorFlow.spec

if errorlevel 1 (
    echo [ERRO] Build falhou!
    pause
    exit /b 1
)

REM Preparar pasta portavel
echo.
echo Preparando pasta portavel...
set OUTPUT_DIR=%~dp0..\app\SectorFlow
if exist "%OUTPUT_DIR%" rmdir /s /q "%OUTPUT_DIR%"
xcopy /E /I /Y "dist\SectorFlow" "%OUTPUT_DIR%"

echo.
echo ========================================
echo   BUILD PORTAVEL CONCLUIDO!
echo ========================================
echo.
echo   Local: app\SectorFlow\
echo   Executar: app\SectorFlow\SectorFlow.exe
echo.
echo   Basta copiar a pasta "app\SectorFlow" para
echo   qualquer outro PC Windows e executar!
echo ========================================
pause
