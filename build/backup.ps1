<#
  backup.ps1
  ----------
  Cria um backup (.zip) do CÓDIGO-FONTE e da configuração do app em
  backups\backup_<data-hora>.zip, para permitir reverter alterações.

  NÃO inclui .venv, dist, tesseract/ nem intermediários de build (regeneráveis).

  Uso:  powershell -ExecutionPolicy Bypass -File build\backup.ps1
#>
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$stamp = Get-Date -Format "yyyy-MM-dd_HHmmss"
$backDir = Join-Path $root "backups"
New-Item -ItemType Directory -Force -Path $backDir | Out-Null

# Itens versionados (código, testes, scripts de build, docs).
$itens = @(
  (Join-Path $root "src"),
  (Join-Path $root "tests"),
  (Join-Path $root "scripts_og"),
  (Join-Path $root "build\build.ps1"),
  (Join-Path $root "build\build_tudo.ps1"),
  (Join-Path $root "build\build_installer.ps1"),
  (Join-Path $root "build\fetch_tesseract.ps1"),
  (Join-Path $root "build\backup.ps1"),
  (Join-Path $root "build\make_icon.py"),
  (Join-Path $root "build\faturas.spec"),
  (Join-Path $root "build\installer.iss"),
  (Join-Path $root "build\app.ico")
)
# Arquivos soltos na raiz (docs, requisitos, gitignore).
Get-ChildItem $root -File -Force | Where-Object {
  ($_.Extension -in ".md", ".txt") -or ($_.Name -like "requirements*") -or ($_.Name -eq ".gitignore")
} | ForEach-Object { $itens += $_.FullName }

$existentes = $itens | Where-Object { Test-Path $_ }
$zip = Join-Path $backDir ("backup_" + $stamp + ".zip")
Compress-Archive -Path $existentes -DestinationPath $zip -CompressionLevel Optimal

$mb = [math]::Round((Get-Item $zip).Length / 1MB, 2)
Write-Host ("OK -> {0} ({1} MB)" -f $zip, $mb)
Write-Host "Para reverter: extraia este .zip por cima da pasta app_faturas."
