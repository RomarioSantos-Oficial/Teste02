param(
    [string]$pfxPath,
    [string]$pfxPassword,
    [string]$exePath = "app\SectorFlow\SectorFlow.exe",
    [string]$timestampUrl = "http://timestamp.digicert.com"
)

if (-not (Test-Path $exePath)) {
    Write-Error "EXE não encontrado: $exePath"
    exit 1
}

if (-not (Test-Path $pfxPath)) {
    Write-Error "PFX não encontrado: $pfxPath"
    exit 1
}

# Procurar signtool
$signtool = "C:\Program Files (x86)\Windows Kits\10\bin\x64\signtool.exe"
if (-not (Test-Path $signtool)) {
    $signtool = Get-Command signtool -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -ErrorAction SilentlyContinue
}

if (-not $signtool) {
    Write-Error "signtool.exe não encontrado. Instale Windows SDK (signtool) ou ajuste o caminho no script."
    exit 1
}

$cmd = "`"$signtool`" sign /f `"$pfxPath`" /p `"$pfxPassword`" /tr `"$timestampUrl`" /td sha256 /fd sha256 `"$exePath`""
Write-Output "Executando: $cmd"
Invoke-Expression $cmd

if ($LASTEXITCODE -ne 0) {
    Write-Error "Assinatura falhou (ExitCode=$LASTEXITCODE). Verifique senha e cert."
    exit $LASTEXITCODE
}

Write-Output "Assinatura concluída com sucesso: $exePath"
