<#
  build_tudo.ps1
  --------------
  Gera TUDO em uma única execução, na ordem correta (sem concorrência entre o
  .zip e o instalador):

    1. Verifica o ambiente (.venv)
    2. Monta o Tesseract portatil (tesseract/) se faltar   -> fetch_tesseract.ps1
    3. Gera o icone (build/app.ico) se faltar              -> make_icon.py
    4. Empacota com o PyInstaller + cria o .zip            -> build.ps1
    5. Gera o instalador setup.exe                         -> build_installer.ps1
       (se o Inno Setup faltar, tenta instalar via winget; se nao der, avisa e pula)

  Uso:
    powershell -ExecutionPolicy Bypass -File build\build_tudo.ps1
    powershell -ExecutionPolicy Bypass -File build\build_tudo.ps1 -PularInstalador

  Saida: dist\FaturasDeEnergia.zip  e  dist\FaturasDeEnergia-Setup.exe
#>
param(
  [switch]$PularInstalador
)

$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$root = Split-Path -Parent $PSScriptRoot
$bdir = $PSScriptRoot

function Passo($txt) { Write-Host "`n========== $txt ==========" -ForegroundColor Cyan }

# 1) ambiente -----------------------------------------------------------------
Passo "1/5  Verificando ambiente"
$py = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
  throw @"
Ambiente .venv nao encontrado. Crie-o uma vez:
  python -m venv .venv
  .\.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-build.txt
"@
}
Write-Host "OK .venv"

# 2) Tesseract portatil -------------------------------------------------------
Passo "2/5  Tesseract (OCR)"
if (Test-Path (Join-Path $root "tesseract\tesseract.exe")) {
  Write-Host "OK tesseract/ ja existe"
} else {
  Write-Host "tesseract/ ausente -> baixando e montando (pode demorar)..."
  & powershell -ExecutionPolicy Bypass -File (Join-Path $bdir "fetch_tesseract.ps1")
  if ($LASTEXITCODE -ne 0) { throw "Falha ao montar o Tesseract." }
}

# 3) icone --------------------------------------------------------------------
Passo "3/5  Icone"
if (Test-Path (Join-Path $bdir "app.ico")) {
  Write-Host "OK build/app.ico ja existe"
} else {
  & $py (Join-Path $bdir "make_icon.py")
}

# 4) empacotar + zip ----------------------------------------------------------
Passo "4/5  PyInstaller + .zip"
& powershell -ExecutionPolicy Bypass -File (Join-Path $bdir "build.ps1")
if ($LASTEXITCODE -ne 0) { throw "Falha no empacotamento (build.ps1)." }

# 5) instalador ---------------------------------------------------------------
$setup = Join-Path $root "dist\FaturasDeEnergia-Setup.exe"
$zip   = Join-Path $root "dist\FaturasDeEnergia.zip"
if ($PularInstalador) {
  Passo "5/5  Instalador (PULADO por -PularInstalador)"
} else {
  Passo "5/5  Instalador (Inno Setup)"
  $cands = @(
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    "C:\Program Files\Inno Setup 6\ISCC.exe",
    (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe")
  )
  $iscc = $cands | Where-Object { Test-Path $_ } | Select-Object -First 1
  if (-not $iscc) {
    Write-Host "Inno Setup ausente -> tentando 'winget install JRSoftware.InnoSetup'..."
    try {
      & winget install --id JRSoftware.InnoSetup -e --accept-source-agreements --accept-package-agreements --scope user | Out-Null
      $iscc = $cands | Where-Object { Test-Path $_ } | Select-Object -First 1
    } catch { }
  }
  if ($iscc) {
    try {
      & powershell -ExecutionPolicy Bypass -File (Join-Path $bdir "build_installer.ps1")
      if ($LASTEXITCODE -ne 0) { Write-Warning "build_installer.ps1 retornou erro $LASTEXITCODE." }
    } catch { Write-Warning ("Instalador nao gerado: " + $_.Exception.Message) }
  } else {
    Write-Warning "Inno Setup indisponivel. O .zip foi gerado; o setup.exe foi pulado."
    Write-Warning "Instale o Inno Setup e rode: build\build_installer.ps1"
  }
}

# Resumo ----------------------------------------------------------------------
Passo "RESUMO"
if (Test-Path $zip)   { Write-Host ("OK  {0}  ({1:N1} MB)" -f $zip,   ((Get-Item $zip).Length/1MB))   -ForegroundColor Green }
if (Test-Path $setup) { Write-Host ("OK  {0}  ({1:N1} MB)" -f $setup, ((Get-Item $setup).Length/1MB)) -ForegroundColor Green }
Write-Host "`nDistribua o .zip (extrair e abrir o .exe) ou o setup.exe (instalador)."
Write-Host "Dica: rode o setup.exe a partir do disco local, nao direto do Google Drive."
