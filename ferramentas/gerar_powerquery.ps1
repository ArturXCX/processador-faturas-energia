<#
  gerar_powerquery.ps1
  --------------------
  Cria um Excel com uma consulta do Power Query por CSV da pasta indicada
  (os CSVs por aba que o modo linha de comando grava com --csv). Cada
  consulta vira uma tabela numa aba; depois e so clicar em
  Dados > Atualizar tudo sempre que os CSVs mudarem.

  A pasta dos CSVs fica num parametro do Power Query ("PastaCSV"): se a
  pasta mudar de lugar, edite-o em Dados > Consultas e Conexoes.

  Uso:  powershell -ExecutionPolicy Bypass -File gerar_powerquery.ps1 -PastaCsv <dir> -Saida <arquivo.xlsx>
  Requer Excel 2016 ou superior instalado (usa a automacao do Excel).
#>
param(
  [Parameter(Mandatory = $true)][string]$PastaCsv,
  [Parameter(Mandatory = $true)][string]$Saida
)
$ErrorActionPreference = "Stop"
$PastaCsv = (Resolve-Path $PastaCsv).Path.TrimEnd('\')
$Saida = [System.IO.Path]::GetFullPath($Saida)
$csvs = Get-ChildItem -Path $PastaCsv -Filter *.csv | Sort-Object Name
if (-not $csvs) { throw "Nenhum CSV em $PastaCsv" }

function TipoColuna([string[]]$valores) {
  $v = $valores | Where-Object { $_ -ne "" }
  if (-not $v) { return "type text" }
  if (($v | Where-Object { $_ -notmatch '^(TRUE|FALSE|True|False)$' }).Count -eq 0) { return "type logical" }
  if (($v | Where-Object { $_ -notmatch '^\d{4}-\d{2}-\d{2}$' }).Count -eq 0) { return "type date" }
  if (($v | Where-Object { $_ -notmatch '^-?\d+(,\d+)?$' }).Count -eq 0) { return "type number" }
  return "type text"
}

function TiposDoCsv([string]$arquivo) {
  # Amostra das primeiras linhas para decidir o tipo de cada coluna.
  $linhas = Get-Content -Path $arquivo -Encoding UTF8 -TotalCount 400
  if (-not $linhas) { return @() }
  $cab = $linhas[0].TrimStart([char]0xFEFF).Split(';')
  $dados = @()
  foreach ($l in ($linhas | Select-Object -Skip 1)) { $dados += , ($l.Split(';')) }
  $tipos = @()
  for ($i = 0; $i -lt $cab.Count; $i++) {
    $col = @()
    foreach ($d in $dados) { if ($i -lt $d.Count) { $col += $d[$i].Trim('"') } }
    $nome = $cab[$i].Trim('"').Replace('"', '""')
    $tipos += ('{"' + $nome + '", ' + (TipoColuna $col) + '}')
  }
  return $tipos
}

$excel = New-Object -ComObject Excel.Application
$excel.Visible = $false
$excel.DisplayAlerts = $false
try {
  $wb = $excel.Workbooks.Add()
  $mPasta = '"' + $PastaCsv.Replace('\', '\\') + '" meta [IsParameterQuery=true, Type="Text", IsParameterQueryRequired=true]'
  $null = $wb.Queries.Add("PastaCSV", $mPasta)

  $primeira = $true
  foreach ($csv in $csvs) {
    $nome = [System.IO.Path]::GetFileNameWithoutExtension($csv.Name)
    $tipos = TiposDoCsv $csv.FullName
    $listaTipos = ($tipos -join ", ")
    $m = @"
let
    Fonte = Csv.Document(File.Contents(PastaCSV & "\$($csv.Name)"), [Delimiter=";", Encoding=65001, QuoteStyle=QuoteStyle.Csv]),
    Cabecalho = Table.PromoteHeaders(Fonte, [PromoteAllScalars=true]),
    Tipos = Table.TransformColumnTypes(Cabecalho, {$listaTipos}, "pt-BR")
in
    Tipos
"@
    $null = $wb.Queries.Add($nome, $m)
    Write-Host ("consulta {0}: {1} coluna(s)" -f $nome, $tipos.Count)
    # Carrega a consulta numa tabela da aba de mesmo nome. Se a automacao da
    # tabela falhar nesta versao do Excel, a consulta continua no arquivo
    # (Dados > Consultas e Conexoes > botao direito > Carregar em...).
    try {
      if ($primeira) { $ws = $wb.Worksheets.Item(1); $primeira = $false } else { $ws = $wb.Worksheets.Add([Type]::Missing, $wb.Worksheets.Item($wb.Worksheets.Count)) }
      $ws.Name = $nome.Substring(0, [Math]::Min(31, $nome.Length))
      $conn = $wb.Connections.Add2("Consulta - $nome", "Consulta '$nome' (Power Query)",
        "OLEDB;Provider=Microsoft.Mashup.OleDb.1;Data Source=`$Workbook`$;Location=$nome;Extended Properties=`"`"",
        "SELECT * FROM [$nome]", 2)
      $lo = $ws.ListObjects.Add(0, $conn, $null, 1, $ws.Range("A1"))
      $lo.Name = "t_$nome"
      try { $lo.QueryTable.Refresh($false) | Out-Null }
      catch { Write-Warning ("Consulta '{0}' criada, mas nao atualizada agora: {1}" -f $nome, $_.Exception.Message) }
    }
    catch {
      Write-Warning ("Consulta '{0}' criada como 'somente conexao': {1}" -f $nome, $_.Exception.Message)
    }
  }

  $leia = $wb.Worksheets.Add($wb.Worksheets.Item(1))
  $leia.Name = "LEIA-ME"
  $leia.Range("A1").Value2 = "Faturas de energia - Power Query"
  $leia.Range("A1").Font.Bold = $true
  $leia.Range("A3").Value2 = "1. Coloque os PDFs novos na pasta de PDFs e rode processar.bat (so os novos sao lidos)."
  $leia.Range("A4").Value2 = "2. Aqui, clique em Dados > Atualizar tudo: cada aba e uma consulta sobre o CSV de mesmo nome."
  $leia.Range("A5").Value2 = "3. Pasta dos CSVs (parametro PastaCSV): " + $PastaCsv
  $leia.Range("A6").Value2 = "   Se mudar de lugar, edite o parametro em Dados > Consultas e Conexoes > PastaCSV."
  $leia.Columns.Item(1).ColumnWidth = 120

  if (Test-Path $Saida) { Remove-Item $Saida -Force }
  $wb.SaveAs($Saida, 51)   # 51 = xlOpenXMLWorkbook
  $wb.Close($false)
  Write-Host "OK -> $Saida"
}
finally {
  $excel.Quit()
  [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($excel)
}
