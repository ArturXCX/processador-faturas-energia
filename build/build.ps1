<#
  build.ps1
  ---------
  Gera o aplicativo distribuivel (pasta + .zip) com o PyInstaller.

  Pre-requisitos (uma vez):
    1) .venv criado e com dependencias:
         python -m venv .venv
         .\.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-build.txt
    2) pasta tesseract/ montada:
         powershell -ExecutionPolicy Bypass -File build\fetch_tesseract.ps1

  Uso:  powershell -ExecutionPolicy Bypass -File build\build.ps1
  Saida: dist\FaturasDeEnergia\  e  dist\FaturasDeEnergia.zip
#>
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$py = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { throw "Ambiente .venv nao encontrado. Veja os pre-requisitos no topo do script." }
if (-not (Test-Path (Join-Path $root "tesseract\tesseract.exe"))) {
  throw "Pasta tesseract/ ausente. Rode build\fetch_tesseract.ps1 primeiro."
}

# Carimbo de data/hora da atualizacao (exibido no app).
$stamp = Get-Date -Format "dd/MM/yyyy HH:mm"
$infoPath = Join-Path $root "src\faturas_app\resources\build_info.txt"
Set-Content -Path $infoPath -Value $stamp -Encoding utf8 -NoNewline
Write-Host ("==> Carimbo de atualizacao: {0}" -f $stamp)

# IMPORTANTE: o PyInstaller empacota em disco LOCAL, nao no Google Drive.
# Empacotar direto no G:\ (Drive) causa corrida de I/O (o Drive move/sincroniza
# o .exe recem-escrito e o os.chmod do PyInstaller falha com WinError 3).
$distLocal = Join-Path $env:LOCALAPPDATA "FaturasBuild\dist"
$workLocal = Join-Path $env:LOCALAPPDATA "FaturasBuild\work"
$appLocal = Join-Path $distLocal "FaturasDeEnergia"

Write-Host "==> Executando PyInstaller (build local em $distLocal)..."
& $py -m PyInstaller "build\faturas.spec" --noconfirm --clean --distpath $distLocal --workpath $workLocal
if ($LASTEXITCODE -ne 0) { throw "PyInstaller falhou (exit $LASTEXITCODE)." }
if (-not (Test-Path (Join-Path $appLocal "FaturasDeEnergia.exe"))) {
  throw "Executavel nao gerado em $appLocal"
}

# Inclui o guia do usuario na pasta distribuida, se existir.
$leia = Join-Path $root "LEIA-ME.txt"
if (Test-Path $leia) { Copy-Item $leia $appLocal -Force }

# .zip gerado a partir do build LOCAL, gravado no Drive (escrita de 1 arquivo).
New-Item -ItemType Directory -Force -Path (Join-Path $root "dist") | Out-Null
Write-Host "==> Compactando em .zip..."
$zip = Join-Path $root "dist\FaturasDeEnergia.zip"
if (Test-Path $zip) { Remove-Item $zip -Force }
Compress-Archive -Path $appLocal -DestinationPath $zip

$sizeMB = [math]::Round((Get-Item $zip).Length/1MB, 1)
Write-Host ""
Write-Host ("OK -> {0} ({1} MB)" -f $zip, $sizeMB)
Write-Host "Build local em: $appLocal"
Write-Host "Distribua esse .zip. A pessoa extrai e roda FaturasDeEnergia\FaturasDeEnergia.exe"
