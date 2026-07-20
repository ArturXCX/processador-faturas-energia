<#
  build_installer.ps1
  -------------------
  Gera o instalador (setup.exe) com o Inno Setup a partir da pasta ja empacotada
  pelo PyInstaller (dist\FaturasDeEnergia\). Rode build\build.ps1 antes.

  Uso:  powershell -ExecutionPolicy Bypass -File build\build_installer.ps1
  Saida: dist\FaturasDeEnergia-Setup.exe
#>
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

# Origem do instalador: o build LOCAL (fora do Google Drive). Fallback: dist\ no Drive.
$appLocal = Join-Path $env:LOCALAPPDATA "FaturasBuild\dist\FaturasDeEnergia"
if (-not (Test-Path (Join-Path $appLocal "FaturasDeEnergia.exe"))) {
  $appLocal = Join-Path $root "dist\FaturasDeEnergia"
}
if (-not (Test-Path (Join-Path $appLocal "FaturasDeEnergia.exe"))) {
  throw "Build nao encontrado (nem local nem em dist\). Rode build\build.ps1 primeiro."
}

# localiza o compilador do Inno Setup
$cands = @(
  "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
  "C:\Program Files\Inno Setup 6\ISCC.exe",
  (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe")
)
$iscc = $cands | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) {
  throw "Inno Setup (ISCC.exe) nao encontrado. Instale com: winget install JRSoftware.InnoSetup"
}

Write-Host "==> Compilando instalador com $iscc (origem: $appLocal)"
& $iscc ("/DSrcDir=" + $appLocal) (Join-Path $PSScriptRoot "installer.iss")
if ($LASTEXITCODE -ne 0) { throw "ISCC falhou (exit $LASTEXITCODE)." }

$setup = Join-Path $root "dist\FaturasDeEnergia-Setup.exe"
if (Test-Path $setup) {
  $mb = [math]::Round((Get-Item $setup).Length/1MB, 1)
  Write-Host ""
  Write-Host ("OK -> {0} ({1} MB)" -f $setup, $mb)
} else {
  throw "Instalador nao gerado."
}
