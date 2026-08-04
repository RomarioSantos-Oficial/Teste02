# ============================================================
#   Build Completo - SectorFlow ALFA
#   Gera EXE + Instalador para Windows
# ============================================================
# Uso: .\build_all.ps1 [-SignWithCert "C:\cert\cert.pfx" -CertPassword "senha"]
# ============================================================

param(
    [string]$SignWithCert = "",
    [string]$CertPassword = ""
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $ProjectRoot

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  SectorFlow ALFA - Build Completo" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 1. Verificar Python
Write-Host "[1/6] Verificando Python..." -ForegroundColor Yellow
$pythonVersion = python --version 2>&1
Write-Host "  $pythonVersion" -ForegroundColor Green

# 2. Instalar dependencias
Write-Host "[2/6] Verificando/Instalando dependencias..." -ForegroundColor Yellow
pip install PySide6 pyinstaller --quiet
Write-Host "  Dependencias OK" -ForegroundColor Green

# 3. Limpar build anterior
Write-Host "[3/6] Limpando builds anteriores..." -ForegroundColor Yellow
if (Test-Path "build") { Remove-Item -Recurse -Force "build" }
if (Test-Path "dist") { Remove-Item -Recurse -Force "dist" }
New-Item -ItemType Directory -Force -Path "build" | Out-Null
Write-Host "  Limpeza OK" -ForegroundColor Green

# 4. Build com PyInstaller
Write-Host "[4/6] Gerando executavel com PyInstaller..." -ForegroundColor Yellow
pyinstaller --clean --noconfirm build\SectorFlow.spec

if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERRO] PyInstaller falhou!" -ForegroundColor Red
    Read-Host "Pressione ENTER para sair"
    exit 1
}
Write-Host "  PyInstaller OK" -ForegroundColor Green

# 5. Copiar para pasta de distribuicao
Write-Host "[5/6] Preparando distribuicao..." -ForegroundColor Yellow
$OutputDir = "app\SectorFlow"
if (Test-Path $OutputDir) { Remove-Item -Recurse -Force $OutputDir }
Copy-Item -Recurse -Force "dist\SectorFlow" $OutputDir
Write-Host "  Distribuido em: $OutputDir" -ForegroundColor Green

# 6. Assinatura (opcional)
if ($SignWithCert -ne "") {
    Write-Host "[6/6] Assinando executavel..." -ForegroundColor Yellow
    .\sign.ps1 -pfxPath $SignWithCert -pfxPassword $CertPassword
    Write-Host "  Assinatura OK" -ForegroundColor Green
} else {
    Write-Host "[6/6] Assinatura pulada (sem certificado)" -ForegroundColor Gray
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  BUILD CONCLUIDO!" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Executavel:     $OutputDir\SectorFlow.exe" -ForegroundColor Green
Write-Host "  Pasta completa: $OutputDir\" -ForegroundColor Green
Write-Host ""
Write-Host "  Para gerar o instalador (.exe setup):" -ForegroundColor Yellow
Write-Host "  1. Instale Inno Setup 6+: https://jrsoftware.org/isinfo.php" -ForegroundColor Yellow
Write-Host "  2. Execute: ISCC.exe build\sectorflow_installer.iss" -ForegroundColor Yellow
Write-Host "  3. O instalador sera gerado em: app\SectorFlow_Setup_0.0.1.exe" -ForegroundColor Yellow
Write-Host ""
Write-Host "  Para distribuir SEM instalador:" -ForegroundColor Yellow
Write-Host "  Copie a pasta $OutputDir para outro PC e execute SectorFlow.exe" -ForegroundColor Yellow
Write-Host ""
