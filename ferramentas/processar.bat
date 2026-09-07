@echo off
setlocal
rem ------------------------------------------------------------------
rem  processar.bat  -  Processador de Faturas de Energia (modo linha de comando)
rem
rem  Uso:  processar.bat [pasta_dos_PDFs] [pasta_de_saida]
rem
rem  Sem argumentos usa as pastas ao lado da pasta do aplicativo:
rem     ..\pdfs   -> PDFs (em subpastas chamadas "equatorial" e "chesp")
rem     ..\saida  -> planilha faturas_energia.xlsx, CSVs por aba e cache
rem
rem  Rode de novo sempre que colocar PDFs novos: so os novos sao lidos
rem  (os demais vem do cache). Depois abra o Excel com Power Query e
rem  clique em Dados > Atualizar tudo.
rem ------------------------------------------------------------------
set "APP=%~dp0FaturasDeEnergiaCLI.exe"
if not exist "%APP%" (
  echo Nao encontrei FaturasDeEnergiaCLI.exe ao lado deste .bat
  pause
  exit /b 1
)
set "PDFS=%~1"
if "%PDFS%"=="" set "PDFS=%~dp0..\pdfs"
set "SAIDA=%~2"
if "%SAIDA%"=="" set "SAIDA=%~dp0..\saida"
if not exist "%PDFS%" (
  echo Pasta de PDFs nao encontrada: %PDFS%
  echo Crie-a com as subpastas "equatorial" e "chesp" ou informe outra: processar.bat "C:\meus\pdfs"
  pause
  exit /b 1
)
if not exist "%SAIDA%" mkdir "%SAIDA%"

"%APP%" --cli --pasta "%PDFS%" --subpastas ^
  --saida "%SAIDA%\faturas_energia.xlsx" ^
  --csv "%SAIDA%\csv" ^
  --cache "%SAIDA%\cache_faturas" ^
  --log "%SAIDA%\processar.log"
set "RC=%ERRORLEVEL%"

if not exist "%SAIDA%\Faturas_PowerQuery.xlsx" (
  echo.
  echo Gerando o Excel com Power Query ^(uma vez^)...
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0gerar_powerquery.ps1" -PastaCsv "%SAIDA%\csv" -Saida "%SAIDA%\Faturas_PowerQuery.xlsx"
)
echo.
if "%RC%"=="0" (echo Concluido. Planilha: %SAIDA%\faturas_energia.xlsx) else (echo Terminou com erro ^(codigo %RC%^). Veja %SAIDA%\processar.log)
pause
exit /b %RC%
