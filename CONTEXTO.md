# CONTEXTO — comece por aqui (handoff para uma nova sessão)

Documento de retomada do projeto **Processador de Faturas de Energia**. Leia
este primeiro; para arquitetura aprofundada veja **[DOCUMENTACAO.md](DOCUMENTACAO.md)**,
para build rápido **[README.md](README.md)**, para uso final **[LEIA-ME.txt](LEIA-ME.txt)**.

Status: **pronto para uso** (esquema v2, jul/2026). Entregáveis atuais em `dist/`:
`FaturasDeEnergia.zip` (~100 MB) e `FaturasDeEnergia-Setup.exe` (~72 MB).

---

## 1. O que é o app (resumo de 30s)

App **desktop Windows** (CustomTkinter, empacotado com PyInstaller — usuário final
**não precisa de Python**) que lê PDFs de faturas de energia da **EQUATORIAL** e da
**CHESP** e gera uma planilha Excel estruturada. Três abas na janela:
1. **Processar faturas**: seleciona pastas de PDFs (cada uma com sua fornecedora),
   processa com barra de progresso, deixa editar/renomear colunas e abas, e salva.
2. **Adicionar a uma planilha**: sobe uma planilha existente (que pode ter sido
   renomeada/editada) e concatena novas faturas, remapeando colunas.
3. **Parâmetros**: tabela de equivalências de itens (editável, persistida).

A lógica de extração foi portada dos notebooks originais em `scripts_og/`.

---

## 2. Caminhos importantes (máquina atual)

- **Raiz do projeto (working dir):**
  `G:\Meu Drive\UFG\Semestre Atual\TJGO\PBI sobre o projeto\dashboard_faturas_energia\app_faturas`
- **Código:** `src/faturas_app/` · **Ambiente:** `.venv/` (Python 3.12)
- **PDFs (dados reais):** `..\pdfs\energia_tjgo\equatorial\{2022,2023_a_2024,2025_a_2026}` e `..\pdfs\energia_tjgo\chesp\{2022,2025_2026}`
- **Conjunto de teste rápido:** `testes_exec\conjunto_faturas\{eq,chesp}` (66 EQ) — use para iterar sem ler as pastas gigantes.
- **Entregáveis:** `dist\` · **Backups do código:** `backups\backup_<data>.zip`
- **Tesseract (OCR) embutido:** `tesseract\` (~46 MB, montado por `build\fetch_tesseract.ps1`)
- **Build LOCAL do PyInstaller:** `%LOCALAPPDATA%\FaturasBuild\` (ver §7)
- **Dados do usuário (equivalências):** `%APPDATA%\FaturasEnergia\equivalencias.json`
- **Mapa de UCs (só existe se importado):** `%APPDATA%\FaturasEnergia\mapa_uc.json`
- **Identificação por medidor (lig/desl):** `%APPDATA%\FaturasEnergia\config_uc.json`
- **Hardcodes do usuário:** `%APPDATA%\FaturasEnergia\hardcodes.json` (nenhum vem embutido)

---

## 3. Como retomar o desenvolvimento (ambiente já existe)

```powershell
# rodar a interface a partir do código:
$env:PYTHONPATH="src"; .\.venv\Scripts\python.exe -m faturas_app

# testes de regressão (lógica de concatenação, sem PDFs):
$env:PYTHONPATH="src"; .\.venv\Scripts\python.exe tests\test_concat.py

# processar via código (exemplo rápido, use o conjunto de teste):
#   from faturas_app.core import equatorial; equatorial.processar_pdf(<pdf>)
```

> **Atenção I/O do Google Drive:** a 1ª leitura de cada PDF vindo do `G:\` (Drive)
> é lenta (streaming da nuvem); depois cacheia. Testes que abrem muitos PDFs podem
> "estourar" o timeout na 1ª execução e rodar rápido na 2ª. Não é bug de código.

Se precisar recriar o ambiente do zero:
```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-build.txt
powershell -ExecutionPolicy Bypass -File build\fetch_tesseract.ps1   # monta tesseract/
```

---

## 4. Estado das funcionalidades (tudo implementado e testado)

- Processar pastas (várias, cada uma EQ ou CHESP) → planilha; editar colunas/abas + renomear; salvar.
- Concatenar novas faturas a uma planilha existente (com remapeamento por metadados
  ou tela de mapeamento); dedup respeitando renomeações.
- **OCR embutido** (Tesseract) para faturas CHESP escaneadas (~22%).
- Coluna **`link_pdf`** (busca no Drive pelo nome do arquivo / modelo de URL).
- **`id_fatura`** com prefixo da fornecedora (`EQUATORIAL_…`/`CHESP_…`) + **`numero_fatura`** (valor original = nome do PDF).
- **`id_uc`** em todas as abas; ausente → **`NULO_<id_fatura>`**. Ao lado, sempre
  nesta ordem: **`id_uc_sem_format`**, **`id_uc_atual_medidor`** (por medidor, o
  id_uc mais recente não-`NULO_`) e **`id_uc_atual_medidor_sem_format`**.
- **`competencia`** em todas as abas exceto `unidade_consumidora`.
- **`medidor`** (só em `fatura`/`fatura_resumida`): medidor (moda) da fatura.
- **`item_normalizado`** (itens): via **Tabela de Equivalências** (aba Parâmetros, persistida).
- **`unidade_consumidora`** (renomeada de `cliente`): **`primeira_competencia`/
  `ultima_competencia`** e **`primeira_fatura`/`ultima_fatura`** (agregados por
  id_uc); **1 linha por UC** via `drop_duplicates()` ao final.
- Abas derivadas **`fatura_resumida`** (1ª, com `valor_total_r$` e `medidor`) e
  **`medicao_resumida`** (só ENERGIA GERAÇÃO - KWH).
- Aba **`glossario`** automática. Dedup só de **linha 100% idêntica** para itens/medição.
- **Nome do arquivo** configurável ao salvar; **carimbo de atualização** no cabeçalho.
- **Backup** de código: `build\backup.ps1`.

### Pendência / decisão a confirmar
`id_uc_atual_medidor` nas abas SEM coluna "Medidor" (fatura, itens_fatura, impostos):
o medidor da linha é inferido pela `id_fatura` (medidor daquela fatura na aba
`medicao`); na `unidade_consumidora`, pelo medidor da UC. Se a regra desejada for
outra, ajustar em `core/derivados.py::_colunas_medidor`.

**TODO adiado de propósito:** `schema.DEDUP_KEYS["unidade_consumidora"]` continua
`["id_uc"]`, não `["id_uc_canonico"]`. Migrar corrigiria a fragmentação de UCs que
mudaram de formato no meio do histórico, mas **reduziria a contagem de linhas** da
aba em relação às planilhas já publicadas/usadas em dashboards. Está documentado
como comentário no próprio `schema.py`, junto de `DEDUP_KEYS`.

---

## 5. Esquema atual das abas (ordem e colunas exatas)

Ordem de saída: `fatura_resumida → fatura → unidade_consumidora → itens_fatura →
tarifas → impostos → medicao → medicao_resumida → glossario` (+ aba oculta
`_faturas_meta`).

Em TODA aba com `id_uc`, logo após ele vêm sempre, nesta ordem:
`id_uc_sem_format, id_uc_atual_medidor, id_uc_atual_medidor_sem_format,
id_uc_canonico` (inseridas programaticamente — ver nota abaixo).

**`id_uc_canonico`** é a coluna recomendada para agrupar por UC — mas ela **só
existe quando há um MAPA DE UCs importado** (`core/dicionario_uc.py`). Ela traz
a UC canônica do cadastro, que une o histórico da mesma UC real mesmo quando o
`id_uc` mudou de formato (`10008414082` → `2.742.876.012-19`) ou o medidor foi
trocado — casos em que `id_uc_atual_medidor` falha. UC fora do mapa cai para o
valor inferido pelo medidor (quando essa identificação está ligada).

Sem mapa: nenhuma aba tem `id_uc_canonico` e a aba `unidade_consumidora` não
recebe coluna nenhuma de cadastro.

A **identificação histórica por medidor** (`id_uc_atual_medidor`,
`id_uc_atual_medidor_sem_format`, `id_uc_atual`) é opcional quando há mapa:
desligada na aba Parâmetros, as três não são criadas em aba nenhuma. Sem mapa
ela é a única identificação que existe e fica sempre ligada.

**fatura**: id_fatura, numero_fatura, arquivo_pdf, link_pdf, fornecedor, id_uc,
id_uc_sem_format, id_uc_atual_medidor, id_uc_atual_medidor_sem_format, medidor,
data_emissao, competencia, data_vencimento, valor_total_r$, numero_nf, serie_nf,
cfop, chave_acesso_nfe, protocolo_autorizacao, data_hora_protocolo,
classificacao_tarifaria, tipo_fornecimento, tensao_nominal_v, tensao_min_v,
tensao_max_v, demanda_contratada_kw, demanda_geracao_contratada_kw,
perdas_transformacao_pct, scee_geracao_ciclo, scee_saldo_kwh_total, scee_saldo_kwh_P,
scee_saldo_kwh_FP, scee_saldo_kwh_HR, data_leitura_anterior, data_leitura_atual,
numero_dias_leitura, data_proxima_leitura

**unidade_consumidora** (renomeada de `cliente`): id_uc, id_uc_sem_format,
id_uc_atual_medidor, id_uc_atual_medidor_sem_format, id_uc_canonico,
razao_social, cnpj, cep, municipio, uf, **+ as colunas do MAPA DE UCs que
estiverem carregadas** (do template: id_uc_aneel_bordero, uc_operante, medidor_atual_dicionario, unidade_institucional, endereco_dicionario, participa_rateio, demanda_futura_kw; mais as colunas extras
que a importação tiver criado),
primeira_competencia, ultima_competencia, primeira_fatura, ultima_fatura
*(sem competencia — é caso à parte)*. **1 linha por UC**: a aba acumula 1 linha
por fatura processada e leva um `drop_duplicates()` ao final (derivados.py) —
como os dados cadastrais e os agregados primeira/ultima_* são iguais para todas
as faturas da mesma UC, sobra 1 linha por UC.

> As colunas de cadastro vêm do MAPA DE UCs importado
> (`core/dicionario_uc.py`). O app NÃO embarca nenhum: sem mapa, a aba não
> recebe nenhuma delas nem `id_uc_canonico`. Item do template não mapeado
> na importação também não vira coluna. `razao_social`/`cnpj`/`cep`/
> `municipio`/`uf` continuam vindo do PDF. **Demanda contratada NUNCA vem
> do mapa** — só da fatura. Booleanos como True/False nativos.

**itens_fatura**: id_fatura, id_uc, id_uc_sem_format, id_uc_atual_medidor,
id_uc_atual_medidor_sem_format, competencia, item, item_normalizado, tipo,
unidade, quantidade, preco_unitario_com_tributos_r$, valor_r$, pis_cofins,
base_calc_icms_r$, aliquota_icms_r$, icms, tarifa_unitaria_r$

**tarifas** *(aba NOVA, derivada de `itens_fatura`)*: fornecedor, competencia,
item, tipo, unidade, preco_unitario_com_tributos_r$, tarifa_unitaria_r$,
item_normalizado. Tabela de REFERÊNCIA (não tem id_fatura nem id_uc): 1 linha
por (fornecedor, item, tarifa_unitaria_r$), na competência em que a combinação
apareceu pela **primeira** vez. Fora: bandeira tarifária (item contém "BAND") e
linhas sem `tarifa_unitaria_r$` (elimina os itens financeiros). Recalculada do
zero no processamento **e** na concatenação (`derivados._derivar_tarifas`) —
concatenar um backfill antigo pode mudar qual linha é "a mais antiga", então a
aba nunca é deduplicada de forma incremental. ~593 linhas no acervo completo.

**impostos**: id_fatura, id_uc, id_uc_sem_format, id_uc_atual_medidor,
id_uc_atual_medidor_sem_format, competencia, Tributo, Base (R$), Aliquota (%),
Valor (R$)

**medicao**: id_fatura, id_uc, id_uc_sem_format, id_uc_atual_medidor,
id_uc_atual_medidor_sem_format, competencia, Grandezas, Postos horarios,
Leitura Anterior, Leitura Atual, Const Medidor, Consumo kWh, Medidor

**fatura_resumida** (derivada de fatura): id_fatura, numero_fatura, id_uc,
id_uc_sem_format, id_uc_atual_medidor, id_uc_atual_medidor_sem_format, medidor,
competencia, valor_total_r$, classificacao_tarifaria, tipo_fornecimento,
demanda_contratada_kw, demanda_geracao_contratada_kw, scee_geracao_ciclo,
scee_saldo_kwh_total, scee_saldo_kwh_P, scee_saldo_kwh_FP, scee_saldo_kwh_HR,
numero_dias_leitura

**medicao_resumida** (derivada de medicao, filtrada em `ENERGIA GERAÇÃO - KWH`,
`Consumo kWh`→`energia_geracao_kwh`): id_fatura, id_uc, id_uc_sem_format,
id_uc_atual_medidor, id_uc_atual_medidor_sem_format, competencia, Grandezas,
Postos horarios, Leitura Anterior, Leitura Atual, Const Medidor,
energia_geracao_kwh, Medidor

> Tudo é definido em `core/schema.py`. O bloco `id_uc_sem_format /
> id_uc_atual_medidor / id_uc_atual_medidor_sem_format` (após id_uc) e
> `item_normalizado` (após item) são inseridos **programaticamente** ao importar
> o módulo — não os procure "escritos à mão" nas listas. `medidor` (fatura/
> fatura_resumida) e as colunas `primeira_*`/`ultima_*` (unidade_consumidora)
> SÃO escritas à mão no schema, mas só recebem valor via `derivados.py` — por
> isso `derivados._reordenar_canonico` reordena tudo para a ordem do schema
> depois de calculado (senão colunas novas caem sempre no final do DataFrame).
>
> Dedup na concatenação: `DEDUP_KEYS` (fatura=id_fatura,
> unidade_consumidora=id_uc, impostos=[id_fatura,Tributo],
> fatura_resumida=id_fatura) vs `DEDUP_FULL_ROW` (itens_fatura, medicao,
> medicao_resumida — só linha 100% idêntica). `unidade_consumidora` leva ainda
> um `drop_duplicates()` final (ver acima), tanto no processamento quanto na
> concatenação.

---

## 6. Mapa de módulos (o que editar para cada coisa)

Núcleo (`src/faturas_app/core/`, sem GUI):
- `schema.py` — **fonte da verdade**: abas, colunas, ordem, cores, dedup, apelidos, protegidas.
- `equatorial.py` / `chesp.py` — processadores; expõem `processar_pdf(path)→{aba: linhas}`.
  `equatorial.carimbar_id_uc_competencia` estampa id_uc/competencia (usado pelos dois).
- `ocr.py` — acha o Tesseract (embutido/sistema).
- `dataset.py` — acumula linhas → DataFrames; **deriva** fatura_resumida/medicao_resumida.
- `profile.py` — camada de exibição (renomear/incluir/excluir) + metadados (`_faturas_meta`).
- `excel_io.py` — escrita estilizada + metadados / leitura.
- `concat.py` — concatenação com remapeamento canônico + dedup.
- `derivados.py` — colunas recalculadas do zero: unidade_consumidora.(primeira|ultima)_*,
  id_uc_atual_medidor(+sem_format), id_uc_canonico + as colunas do mapa de UCs,
  medidor (fatura/fatura_resumida), item_normalizado e a aba `tarifas` inteira
  (`aplicar` no processamento, `aplicar_concat` na concatenação). **A ORDEM das
  chamadas em `_calcular` importa**: `_colunas_medidor` → `_enriquecer_dicionario_uc`
  → `_extremos_por_uc` (que agora agrupa por `id_uc_canonico`) → `_item_normalizado`
  → `_derivar_tarifas` → `_tipo_fornecimento_upper` → `_reordenar_canonico`.
- `dicionario_uc.py` — cadastro OFICIAL de UCs: resolve o `id_uc` em qualquer
  formato (índice por dígitos sobre UC/UC VELHA/UC FORMATADO) e devolve as 28
  colunas cadastrais. Sem semente embutida: o cadastro é importado pela aba
  Parâmetros (`%APPDATA%\FaturasEnergia\dicionario_uc.json`), com casamento
  tolerante de nomes de campo (`analisar`).
- `equivalencias.py` — tabela item→item_normalizado (JSON em %APPDATA%).
- `links.py` — coluna link_pdf. `glossario.py` — aba glossario. `build_info.py` — carimbo.
- `controller.py` — orquestra o processamento das pastas (progresso/cancelar).

Interface (`src/faturas_app/gui/`):
- `app.py` — janela + 3 abas + handler global de erros + cabeçalho (carimbo, OCR, tema).
- `tab_processar.py`, `tab_concatenar.py`, `tab_parametros.py` — as três abas.
- `columns_editor.py`, `mapping_dialog.py`, `widgets.py`, `worker.py` — apoio.

Como adicionar coisas: ver DOCUMENTACAO.md §7 (coluna nova, aba derivada, distribuidora nova).

---

## 7. Build, testes e backup

**Build (gera .zip + setup.exe):**
```powershell
powershell -ExecutionPolicy Bypass -File build\build_tudo.ps1
# -PularInstalador  -> só o .zip
```
Orquestra: provisiona o que faltar (tesseract, ícone, Inno Setup via winget) →
PyInstaller → .zip → instalador. **Empacota em disco LOCAL** (`%LOCALAPPDATA%\FaturasBuild`)
porque empacotar direto no Drive causa corrida de I/O (PyInstaller `os.chmod` falha
com WinError 3). Só o `.zip` e o `setup.exe` são gravados no Drive (`dist\`).

**Validar o `.exe`** (sem abrir janela): rode com a env `FATURAS_SELFCHECK=<arquivo>`
apontando o exe do build local (`%LOCALAPPDATA%\FaturasBuild\dist\FaturasDeEnergia\FaturasDeEnergia.exe`);
ele grava um relatório (imports/OCR/glossário) e sai. A contagem de termos do
glossário muda quando o código muda → confirma que o pacote é a versão nova.

**Backup do código antes de mexer:**
```powershell
powershell -ExecutionPolicy Bypass -File build\backup.ps1   # -> backups\backup_<data>.zip
```
Reverter: extraia o `.zip` por cima de `app_faturas`.

---

## 8. Pegadinhas / decisões que já custaram tempo (não repita)

- **`self._w` é reservado do Tkinter** (caminho da janela). NUNCA use `_w` como
  atributo em widgets — quebra todo `grid()`. (Já mordeu; o editor usa `_widgets`.)
- **App sem console**: exceções em callbacks somem → há handler global
  (`App._erro_inesperado`) que avisa e grava `~/faturas_erro.log`.
- **Layout**: o rodapé (botão Salvar) é fixado com `pack(side="bottom")` para ficar
  sempre visível; o resto rola. Não voltar a empilhar tudo em `grid`.
- **OCR / Tesseract**: o build conda-forge importa `libcurl.dll` que NÃO vem como
  dependência automática → `fetch_tesseract.ps1` instala `tesseract libcurl` juntos
  (senão o exe dá `0xC0000135`). UB-Mannheim dá 403 a download automatizado.
- **Google Drive x build**: empacotar no Drive falha (WinError 3) e o ISCC trava →
  build local (§7). Rodar o `setup.exe` direto do Drive também trava a instalação —
  copiar para o disco local antes.
- **Dedup**: itens_fatura/medicao/medicao_resumida só removem linha 100% idêntica.
- **id_uc antigo (Equatorial)**: fallbacks por época em `_extrair_id_uc` (PERDAS / NOTA FISCAL).
- **CHESP escaneada**: competencia via NOME do arquivo (mês por extenso); id_uc com
  regex tolerante a ruído de OCR (rótulo `UNIDADE CONSUMIDORA:` e rodapé `MM/AAAA <uc> … 905`).
- **Reconciliação** (validação de itens): soma `valor_r$` por `id_fatura` ≈
  `valor_total_r$` (tol. R$1). Exceções LEGÍTIMAS: itens `UFER DEMONSTRATIVO*`
  (informativos, não somam no total) e faturas ESCANEADAS (itens ilegíveis por OCR).
- **PDFs com VÁRIAS faturas mescladas** (ex.: `PDFsam_merge.pdf`, 182 faturas):
  `equatorial.processar_pdf_multi` divide pela âncora "DOCUMENTO AUXILIAR…" e
  devolve LISTA de resultados; o controller aceita dict ou lista. `processar_pdf`
  continua single (compatibilidade).
- **Planilhas geradas ANTES de 15/jul/2026** têm itens de 2022/2023 errados
  (layout antigo). A concatenação NÃO corrige linhas existentes (dedup mantém a
  antiga) — reprocessar as pastas DO ZERO e gerar planilha nova. O build em
  `dist/` (12/07) é anterior aos fixes: refazer `build\build_tudo.ps1` antes de
  redistribuir.
- **Dedup no PROCESSAMENTO**: `Dataset.adicionar_resultado` ignora faturas com
  `id_fatura` repetido no lote (o merge PDFsam repete 182 faturas que também
  existem como PDFs individuais).
- **CHESP "Modelo 6"** (jan–mai/2022, 18 faturas): o corpo fica na PÁGINA 1
  (a pg 0 só tem o cabeçalho); parser próprio em `chesp._extrair_itens_modelo6`.
  Os preços do Modelo 6 NÃO embutem tributos — o item "TRIBUTOS (PIS/COFINS)"
  (impresso na própria fatura) fecha a soma com o total. A **demanda contratada**
  desse layout vem no cabeçalho (`DEMANDA CONTR.: 60`), fora do bloco
  `GRANDEZAS CONTRATADAS` do layout colorido — regex próprio, como 3ª tentativa,
  em `chesp.extrair_fatura_chesp`. O "CONTR" é o que separa esse rótulo da linha
  do ITEM "DEMANDA 60 18,92000 1.135,20" mais adiante na mesma fatura.
- **Demanda contratada ausente = NULO, não 0** (`demanda_contratada_kw` /
  `demanda_geracao_contratada_kw`, EQ e CHESP): 0 é um valor que a fatura pode
  imprimir de verdade, então usá-lo como "ausente" apagava a diferença entre
  "a fatura não tem o campo" e "a fatura diz 0". **Reprocessar do zero** para
  corrigir planilhas antigas — concatenar não reescreve linha já existente.
- **CHESP OCR**: unidades ruidosas ("kWwh"/"kWw") toleradas; `_valor_confiavel`
  recalcula valor=qtd×preço quando o impresso destoa (vírgula perdida/dígito
  trocado) e o preço é crível vs a tarifa. Validação 15/07: 198/198 CHESP e
  99,86%+ EQ reconciliadas.
- **FATURAS_SELFCHECK** é o arquivo de SAÍDA do relatório (o app ESCREVE nele) —
  nunca apontar para um arquivo que não possa ser sobrescrito.
- **Colunas do mapa de UC são DINÂMICAS.** `schema.CANONICAL_COLUMNS` lista as
  7 colunas do template só para fixar a ORDEM; quem cria (ou não) é
  `derivados._enriquecer_mapa_uc`, conforme o que o usuário mapeou na
  importação. Sem mapa, nenhuma delas — e nenhuma aba tem `id_uc_canonico`.
- **`unidade_judiciaria` virou `unidade_institucional`** (nome genérico, o app
  não é só do Judiciário).
- **Nada de dados de instituição embutidos no app.** Não existem mais
  `resources/hardcodes_padrao.json` nem `resources/dicionario_uc.json`: eram do
  TJGO e iam para todo mundo que instalasse. `hardcodes.padrao()` devolve `[]`
  sempre, e o dicionário só existe se o usuário importar. Não voltar a semear.
- **Identidade do borderô vem do CONTEÚDO, não do nome do arquivo.** O parser
  antigo trazia `4000000225` (o código de agrupamento do TJGO) escrito no regex
  do NOME — renomear o PDF zerava a identidade. Hoje número, competência,
  vencimento e código saem do cabeçalho impresso; o nome é último recurso.
  EXCEÇÃO conhecida: em todo 2022 e jan–set/2023 a marca da concessionária não
  está no texto (cabeçalho é imagem), então ali a `distribuidora` vem mesmo do
  nome do arquivo. O layout da tabela NÃO serve de substituto — jun–set/2023
  são borderôs da EQUATORIAL ainda no template da ENEL.
- **Borderô: competência é `AAAA-MM` e vencimento `AAAA-MM-DD`** (eram
  `MM/AAAA` e `dd/mm/aaaa`), para cruzar com a planilha de faturas.
- **Pós-processamento NÃO roda na thread da interface.** `to_dataframes` +
  `derivados` + `hardcodes` + `Perfil` são proporcionais ao LOTE inteiro: com
  10 mil faturas isso levava minutos e, rodando na thread do Tk, a janela
  parava de responder logo após o último PDF — parecia travamento no último
  arquivo, mas era o laço de eventos bloqueado. Fica em thread própria
  (`tab_processar._pos_processar`); não voltar a chamar direto do `_poll`.
- **Consulta ao dicionário é por id_uc DISTINTO, não por linha.** São ~400 UCs
  para dezenas de milhares de linhas; consultar por linha dominava o tempo do
  pós-processamento.
- **Texto colado no fim da linha de medição** (Equatorial): o pdfplumber gruda
  texto legal ("CONFORME REN. ANEEL 414/10.") no fim da linha. Por isso os
  padrões de linha truncada usam um lookahead "não vem outro número depois"
  (`FIM`) em vez de âncora de fim de linha — não voltar a usar `$` ali.

---

## 9. Referências

- **DOCUMENTACAO.md** — arquitetura detalhada, fluxo, como estender.
- **README.md** — build. **LEIA-ME.txt** — uso final (vai dentro do .zip).
- **scripts_og/** — notebooks originais (Equatorial/CHESP/concatenador) que embasam a extração.
- Memória do Claude Code deste projeto: resumo em `MEMORY.md` (índice) + `app-faturas-energia.md`.
