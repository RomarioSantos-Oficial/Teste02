# ============================================================
#   Build Completo - SectorFlow Overley
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
Write-Host "  SectorFlow Overley 0.0.5 - Build Completo" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 1. Verificar Python
Write-Host "[1/6] Verificando Python..." -ForegroundColor Yellow
$pythonVersion = python --version 2>&1
Write-Host "  $pythonVersion" -ForegroundColor Green

# 2. Usar o ambiente virtual do projeto
Write-Host "[2/6] Verificando dependencias..." -ForegroundColor Yellow
$PythonExe = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $PythonExe)) {
    throw "Ambiente virtual nao encontrado: $PythonExe"
}
& $PythonExe -c "import PySide6, PyInstaller, websockets"
if ($LASTEXITCODE -ne 0) {
    throw "Dependencias de build ausentes. Execute: .venv\Scripts\python.exe -m pip install -r requirements.txt"
}
Write-Host "  Dependencias OK" -ForegroundColor Green

# 3. Limpar build anterior
Write-Host "[3/6] Limpando builds anteriores..." -ForegroundColor Yellow
if (Test-Path "build\work") { Remove-Item -Recurse -Force "build\work" }
if (Test-Path "dist\SectorFlow") { Remove-Item -Recurse -Force "dist\SectorFlow" }
Write-Host "  Limpeza OK" -ForegroundColor Green

# 4. Build com PyInstaller
Write-Host "[4/6] Gerando executavel com PyInstaller..." -ForegroundColor Yellow
& $PythonExe -m PyInstaller --clean --noconfirm --workpath build\work build\SectorFlow.spec

if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller falhou."
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
$InnoCandidates = @(
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    "C:\Program Files\Inno Setup 6\ISCC.exe",
    (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe")
)
$InnoCompiler = $InnoCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $InnoCompiler) {
    throw "Inno Setup 6 nao encontrado nos caminhos de sistema ou do usuario."
}
Write-Host "  Gerando instalador com Inno Setup 6..." -ForegroundColor Yellow
& $InnoCompiler "/Q" "build\sectorflow_installer.iss"
if ($LASTEXITCODE -ne 0) { throw "Inno Setup falhou." }
Write-Host "  Instalador: app\SectorFlow_Setup_0.0.5.exe" -ForegroundColor Green
Write-Host ""
Write-Host "  Para distribuir SEM instalador:" -ForegroundColor Yellow
Write-Host "  Copie a pasta $OutputDir para outro PC e execute SectorFlow.exe" -ForegroundColor Yellow
Write-Host ""
