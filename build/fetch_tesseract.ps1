<#
  fetch_tesseract.ps1
  --------------------
  Monta a pasta portatil `tesseract/` (motor de OCR usado para faturas CHESP
  escaneadas). Usa o micromamba para baixar o Tesseract do conda-forge com TODAS
  as DLLs necessarias e o idioma portugues. Reproduzivel: rode uma vez antes do
  primeiro build (ou quando quiser atualizar o Tesseract).

  Uso:  powershell -ExecutionPolicy Bypass -File build\fetch_tesseract.ps1
#>
$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$root     = Split-Path -Parent $PSScriptRoot          # ...\app_faturas
$stage    = Join-Path $PSScriptRoot "_stage"
$portable = Join-Path $root "tesseract"
New-Item -ItemType Directory -Force -Path $stage | Out-Null

# 1) micromamba (binario unico)
$mm = Join-Path $stage "micromamba.exe"
if (-not (Test-Path $mm)) {
  Write-Host "Baixando micromamba..."
  & curl.exe -L --fail --silent --show-error -o $mm `
    "https://github.com/mamba-org/micromamba-releases/releases/latest/download/micromamba-win-64.exe"
}

# 2) idioma portugues (tessdata padrao)
$por = Join-Path $stage "por.traineddata"
if (-not (Test-Path $por)) {
  Write-Host "Baixando por.traineddata..."
  & curl.exe -L --fail --silent --show-error -o $por `
    "https://github.com/tesseract-ocr/tessdata/raw/main/por.traineddata"
}

# 3) cria env conda-forge com tesseract + libcurl (dependencia de runtime)
$prefix = Join-Path $stage "tess_env"
$env:MAMBA_ROOT_PREFIX = Join-Path $stage "mmroot"
Write-Host "Resolvendo Tesseract no conda-forge (pode demorar)..."
& $mm create -p $prefix -c conda-forge tesseract libcurl -y --no-rc | Out-Null

$bin   = Join-Path $prefix "Library\bin"
$tdsrc = Join-Path $prefix "Library\share\tessdata"
$texe  = Join-Path $bin "tesseract.exe"
if (-not (Test-Path $texe)) { throw "tesseract.exe nao foi criado pelo micromamba." }

# 4) monta a pasta portatil: exe + todas as DLLs + tessdata (por, e eng/osd se houver)
New-Item -ItemType Directory -Force -Path (Join-Path $portable "tessdata") | Out-Null
Copy-Item $texe $portable -Force
Copy-Item (Join-Path $bin "*.dll") $portable -Force
foreach ($f in @("eng.traineddata", "osd.traineddata")) {
  $p = Join-Path $tdsrc $f
  if (Test-Path $p) { Copy-Item $p (Join-Path $portable "tessdata") -Force }
}
Copy-Item $por (Join-Path $portable "tessdata") -Force

# 5) valida
Push-Location $portable
$ver = (& ".\tesseract.exe" --version 2>&1 | Select-Object -First 1)
Pop-Location
$sizeMB = [math]::Round(((Get-ChildItem $portable -Recurse | Measure-Object Length -Sum).Sum/1MB),1)
Write-Host ("OK -> tesseract/ pronto: {0} ; {1} MB" -f $ver, $sizeMB)
Write-Host "Voce pode apagar build\_stage para liberar espaco."
