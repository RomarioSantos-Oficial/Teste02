@echo off
REM =============================================================
REM   Build Script - SectorFlow ALFA (Windows Executable)
REM =============================================================
REM   Este script gera o executável SectorFlow.exe usando PyInstaller.
REM   Requisitos:
REM     - Python 3.10+ instalado
REM     - PySide6 instalado (pip install PySide6)
REM     - PyInstaller instalado (pip install pyinstaller)
REM     - Executar na raiz do projeto (onde está run.py)
REM =============================================================

echo.
echo ========================================
echo   SectorFlow ALFA - Build Windows EXE
echo ========================================
echo.

REM Verificar Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERRO] Python nao encontrado. Instale Python 3.10+
    pause
    exit /b 1
)

REM Verificar dependencias
echo [1/4] Verificando dependencias...
pip show PySide6 >nul 2>&1
if errorlevel 1 (
    echo [INFO] Instalando PySide6...
    pip install PySide6
)

pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo [INFO] Instalando PyInstaller...
    pip install pyinstaller
)

REM Verificar vendor/pyLMUSharedMemory
if not exist "vendor\pyLMUSharedMemory\lmu_data.py" (
    echo.
    echo [AVISO] pyLMUSharedMemory nao encontrado em vendor\pyLMUSharedMemory\
    echo O executavel ira funcionar, mas a leitura de memoria compartilhada
    echo do LMU so funcionara se o Le Mans Ultimate estiver rodando.
    echo.
)

REM Limpar build anterior
echo [2/4] Limpando build anterior...
if exist "build" rmdir /s /q build
if exist "dist" rmdir /s /q dist

REM Executar PyInstaller
echo [3/4] Gerando executavel com PyInstaller...
pyinstaller --clean --noconfirm build\SectorFlow.spec

if errorlevel 1 (
    echo.
    echo [ERRO] Build falhou! Verifique os erros acima.
    pause
    exit /b 1
)

REM Criar pasta de distribuicao
echo [4/4] Preparando pacote de distribuicao...
set DISTRIBUTION_DIR=dist\SectorFlow
set OUTPUT_DIR=%~dp0..\app\SectorFlow

REM Criar diretorio de saida
if exist "%OUTPUT_DIR%" rmdir /s /q "%OUTPUT_DIR%"
mkdir "%OUTPUT_DIR%"

REM Copiar tudo do build para pasta de distribuicao
xcopy /E /I /Y "%DISTRIBUTION_DIR%" "%OUTPUT_DIR%"

echo.
echo ========================================
echo   BUILD CONCLUIDO COM SUCESSO!
echo ========================================
echo.
echo   Executavel: app\SectorFlow\SectorFlow.exe
echo.
echo   Para instalar em outro PC, copie toda a pasta
echo   "app\SectorFlow" para o computador destino.
echo   Ou use o instalador (instrucoes abaixo).
echo.
echo ========================================
pause
