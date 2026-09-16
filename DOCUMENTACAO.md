# Documentação técnica — Processador de Faturas de Energia

Guia de manutenção do app: **o que ele faz, como faz, e como alterá-lo** em
sessões futuras. Para uso do usuário final, veja [LEIA-ME.txt](LEIA-ME.txt);
para build rápido, o [README.md](README.md).

> **Retomando numa nova sessão?** Comece por **[CONTEXTO.md](CONTEXTO.md)**
> (handoff: ambiente, caminhos, estado atual de cada feature, esquema completo,
> pendências). Este arquivo aprofunda a arquitetura.

---

## 1. O que o app faz

App desktop Windows (CustomTkinter, empacotado com PyInstaller — **não exige
Python instalado**) que lê PDFs de faturas de energia de **duas distribuidoras**
(EQUATORIAL e CHESP) e gera uma planilha Excel estruturada. Duas telas:

1. **Processar faturas**: seleciona pastas de PDFs (cada uma com sua fornecedora),
   processa com barra de progresso, deixa editar/renomear colunas e abas, e salva.
2. **Adicionar a uma planilha**: sobe uma planilha existente (que pode ter sido
   renomeada/editada) e concatena novas faturas, remapeando colunas.

E um **modo linha de comando** (`FaturasDeEnergiaCLI.exe --cli …`, ou
`processar.bat`) para rotina sem interface: pool de processos, cache JSON por
PDF (só os novos são lidos) e CSV por aba para um Excel com Power Query — ver
§4 e `ferramentas/`.

Recursos transversais: **OCR embutido** (faturas CHESP escaneadas), coluna de
**link do PDF**, **mapa de UCs** (cadastro importado pelo usuário), aba de
**validação** do lote, **glossário** automático, **nome do arquivo**
configurável, e carimbo de **última atualização**.

---

## 2. Abas e colunas da planilha gerada

Ordem de saída: `fatura_resumida` → `fatura` → `unidade_consumidora` →
`itens_fatura` → `tarifas` → `impostos` → `medicao` → `medicao_resumida` →
`validacao` → `glossario` (+ aba oculta `_faturas_meta` com metadados).

| Aba | Conteúdo | Origem |
|---|---|---|
| `fatura` | 1 linha/fatura: id, datas, valor, medidor, dados fiscais, classificação, SCEE, leituras | processador |
| `unidade_consumidora` | dados da UC (razão social, CNPJ, endereço, primeira/última competência e fatura) + o cadastro do MAPA DE UCs, quando houver; **1 linha por UC** (drop_duplicates ao final) | processador + `core/dicionario_uc.py` |
| `itens_fatura` | itens (energia, demanda, tributos, ajustes); tem `id_uc` | processador |
| `tarifas` | tabela de referência: 1 linha por (`fornecedor`, `item`, `tarifa_unitaria_r$`), na competência em que a combinação apareceu pela 1ª vez | **derivada** de `itens_fatura` |
| `impostos` | PIS/PASEP, COFINS, ICMS | processador |
| `medicao` | grandezas medidas por posto horário | processador |
| `fatura_resumida` | **1ª aba**; subconjunto de `fatura` (inclui `valor_total_r$` e `medidor`) | **derivada** de `fatura` |
| `medicao_resumida` | `medicao` só de `ENERGIA GERAÇÃO - KWH`, `Consumo kWh`→`energia_geracao_kwh` | **derivada** de `medicao` |
| `validacao` | 1 linha por ocorrência (`gravidade` erro/aviso/info, `regra`, `detalhe`): demanda × grupo AT/BT do mapa, UC fora do mapa, soma de itens × total, medição vazia/incompleta, fatura lida por OCR | **derivada** (`derivados._derivar_validacao`) |
| `glossario` | significado de colunas/valores/itens/regras (470+ termos) | `core/glossario.py` |

A aba **`validacao`** é o cruzamento que a fatura sozinha não permite: o grupo
de tensão da fatura (`grupo_da_classificacao`: `A A4 …`/`A4 - …` → A; `B B3 …`
→ B; `A OPT B3` → A, porque a UC optante pela tarifa B continua em alta tensão
com demanda contratada — 4 UCs em 2022) contra o grupo de fornecimento do
MAPA DE UCs (qualquer coluna extra cujo nome fale em fornecimento/grupo e cujos
valores tragam `AT`/`BT`, ex.: `FORNECIMENTO (GRUPO AT/BT)` = `TRIFÁSICO (AT)`).
Regras e gravidades estão no docstring de `_derivar_validacao` e na categoria
"Regra de validação" do glossário. Recalculada do zero em todo processamento e
concatenação, como `tarifas` (`derivados.ABAS_RECALCULADAS`); sem mapa, sai sem
a coluna `id_uc_canonico` (mesma regra das outras abas).

A aba **`tarifas`** guarda a linha do tempo das tarifas: nomes de item mudam
quando a distribuidora reformula a fatura, mas a tarifa numérica por trás
costuma ser estável dentro do mesmo enquadramento. Ficam de fora a bandeira
tarifária (item contém `BAND` — é proporcional aos dias de vigência de cada
fatura, não uma propriedade estável do item) e as linhas sem
`tarifa_unitaria_r$` (o que elimina os itens financeiros). `fornecedor` faz
parte da chave porque CHESP e Equatorial chegam a coincidir no valor da tarifa
de `DEMANDA` em dezembro. Calculada em `derivados._derivar_tarifas`, do zero, a
cada processamento **e** a cada concatenação — a regra "mantém a competência
mais antiga" só fecha olhando o conjunto completo.

Colunas-chave especiais:
- **`id_fatura`** leva prefixo da fornecedora (`EQUATORIAL_…`/`CHESP_…`) e liga
  todas as abas. **`numero_fatura`** guarda o valor original (= nome do PDF no
  Drive — preserva a busca do `link_pdf`).
- **`id_uc`** aparece em TODAS as abas; quando a fatura não traz UC, recebe
  `NULO_<id_fatura>` (nunca vazio — feito em `equatorial.carimbar_id_uc_competencia`,
  usado também pela CHESP). Logo ao lado, sempre nesta ordem: **`id_uc_sem_format`**
  (sem ponto/hífen), **`id_uc_atual_medidor`** (por medidor, o id_uc mais recente
  e não-`NULO_`) e **`id_uc_atual_medidor_sem_format`**, e por fim
  **`id_uc_canonico`**. **`competencia`** aparece em todas as abas exceto
  `unidade_consumidora`.
- **`id_uc_canonico`** (todas as abas com `id_uc`): a UC segundo o MAPA DE UCs.
  Ela **só existe quando há um mapa importado**: é a UC canônica do
  cadastro, que une o histórico da mesma UC real mesmo quando o `id_uc` mudou de
  formato (`10008414082` → `2.742.876.012-19`) ou o medidor foi trocado — casos
  em que `id_uc_atual_medidor` falha. UC fora do mapa cai para o valor inferido
  pelo medidor, quando essa identificação está ligada.

  Sem mapa, NENHUMA aba tem `id_uc_canonico`.

  **É a coluna recomendada para agrupar por UC** (ex.: no Power BI).
  `schema.DEDUP_KEYS["unidade_consumidora"]` continua sendo `id_uc` — migrar
  mudaria a contagem de linhas de planilhas já publicadas (decisão adiada, com
  `TODO` no `schema.py`).
- **Cadastro do mapa de UCs** (em `unidade_consumidora`, entre `uf` e
  `primeira_competencia`): as colunas do template que a importação mapeou
  (id_uc_aneel_bordero, uc_operante, medidor_atual_dicionario, unidade_institucional, endereco_dicionario, participa_rateio, demanda_futura_kw) mais as colunas extras
  criadas na importação. Vêm do arquivo que o usuário importou; item não
  mapeado não vira coluna. `razao_social`/`cnpj`/`cep`/`municipio`/`uf`
  continuam vindo do PDF. **Demanda contratada nunca vem do mapa.**
- **Identificação por medidor** (`id_uc_atual_medidor`,
  `id_uc_atual_medidor_sem_format`, `id_uc_atual`): opcional quando há mapa
  (aba Parâmetros). Desligada, as três somem de todas as abas.
- **`demanda_contratada_kw` / `demanda_geracao_contratada_kw`** vêm SEMPRE do
  PDF da fatura. Ficam **vazias** quando a fatura não traz o campo de grandezas
  contratadas; `0` quando a fatura imprime esse valor explicitamente (antes,
  ausência e zero eram gravados igual) **ou quando a UC do grupo A é faturada
  "S/ CONTRATO"** (itens `CONSUMO/DEMANDA S/ CONTRATO`; a caixa vem vazia
  justamente porque não há contrato — UC 10037643922, ago–dez/2023). A CHESP
  "Modelo 6" (nota antiga P&B, jan–mai/2022) imprime esse valor no cabeçalho
  (`DEMANDA CONTR.: 60`), fora do bloco `GRANDEZAS CONTRATADAS` do layout
  colorido — há um regex próprio para ele em `chesp.py`; nas CHESP escaneadas o
  rótulo da caixa pode sair corrompido pelo OCR (`Danenda fm panesam 100`) e há
  um regex tolerante + um último recurso pela linha do item `DEMANDA kW …` (só
  no grupo A).
- **`mensagens_importantes`** (`fatura`/`fatura_resumida`): a caixa de mensagens
  da fatura. Equatorial: começa depois da linha do total (`AGO/2023 30/09/2023
  R$***…` ou, no layout 2025+, `JUL/2026 R$***… 30/08/2026`) e vai até a
  primeira linha de tabela (tributos/itens/medição/histórico) —
  `equatorial.extrair_mensagens`. CHESP: entre a linha do protocolo e o
  cabeçalho `Itens de fatura` (`Bandeira Tarifária …`); no Modelo 6, a linha da
  bandeira no cabeçalho — `chesp.extrair_mensagens_chesp`. Caixa vazia → vazio.
- **`extraido_por_ocr`** (`fatura`): `True` quando o texto veio do Tesseract
  (`extrair_texto_info`/`extrair_texto_chesp_info` devolvem `(texto, usou_ocr)`).
- **`medidor`** (só em `fatura`/`fatura_resumida`): medidor (moda) da fatura,
  vindo da aba `medicao`.
- **`unidade_consumidora.primeira_competencia` / `ultima_competencia` /
  `primeira_fatura` / `ultima_fatura`**: extremos cronológicos agregados por
  `id_uc`, recalculados por `derivados.py` no processamento e na concatenação
  (do zero). A aba acumula 1 linha por FATURA; um `drop_duplicates()` final
  (mesmos dados cadastrais + mesmos agregados ⇒ mesma UC) deixa 1 linha por UC.
- **`item_normalizado`** (em `itens_fatura`): vem da tabela de equivalências
  (`equivalencias.py`, aba Parâmetros). Recalculado do zero em
  `derivados.aplicar` / `aplicar_concat`, assim como as colunas de `id_uc` acima.
- CHESP escaneada: `competencia` cai no fallback pelo NOME do arquivo (mês em
  extenso, ex.: `OUTUBRO.2025`); `id_uc` tem regexes tolerantes a ruído de OCR
  (rótulo `UNIDADE CONSUMIDORA:` e rodapé `MM/AAAA <uc> … 905`).
- **`scee_geracao_ciclo`** (AAAA_MM) e **`scee_saldo_kwh_total` / `_P` / `_FP` /
  `_HR`**: do bloco "INFORMAÇÕES DO SCEE" (só Equatorial, UCs do SCEE).
- **`caminho_pdf`** (caminho local) e **`link_pdf`** (link do Drive, configurável).

---

## 3. Arquitetura

```
src/faturas_app/
├── __init__.py          APP_NAME, __version__
├── __main__.py          entrada: GUI, `--cli …` ou selfcheck (env FATURAS_SELFCHECK=<arquivo>); multiprocessing.freeze_support()
├── cli.py               modo linha de comando: pool de processos, cache JSON por PDF, CSV por aba, importação do mapa sem perguntas
├── core/                NÚCLEO — sem dependência de GUI (testável isolado)
│   ├── schema.py        ESQUEMA CANÔNICO: abas, colunas, cores, chaves de dedup, apelidos
│   ├── equatorial.py    processador Equatorial (regexes portadas do notebook)
│   ├── chesp.py         processador CHESP + OCR
│   ├── ocr.py           localiza o Tesseract (embutido ou do sistema)
│   ├── dataset.py       acumula linhas → DataFrames; DERIVA fatura_resumida/medicao_resumida
│   ├── profile.py       camada de EXIBIÇÃO (renomear/incluir/excluir) + metadados
│   ├── excel_io.py      escrita estilizada + aba oculta de metadados / leitura
│   ├── concat.py        concatenação com remapeamento canônico + dedup
│   ├── links.py         gera coluna link_pdf (busca no Drive pelo nome / modelo)
│   ├── derivados.py     colunas recalculadas do zero: unidade_consumidora.(primeira|ultima)_*, id_uc_atual_medidor(+sem_format), id_uc_canonico, medidor, item_normalizado, e as abas `tarifas` e `validacao` inteiras
│   ├── dicionario_uc.py MAPA DE UCs importado pelo usuário (%APPDATA%/mapa_uc.json; o app não embarca nenhum): TEMPLATE, importação com mapeamento (analisar_arquivo/aplicar_mapeamento — chave escolhível, identificadores alternativos, sugestões por nome), id_uc_canonico e as colunas de cadastro. Guarda também se a identificação por medidor está ligada
│   ├── equivalencias.py tabela item→item_normalizado persistida em %APPDATA%/FaturasEnergia
│   ├── hardcodes.py     regras SE→ENTÃO do usuário (erro da concessionária), persistidas em %APPDATA%/FaturasEnergia
│   ├── glossario.py     monta a aba glossario (docs + conceitos + itens do PDF)
│   ├── build_info.py    lê o carimbo de data/hora da última atualização
│   └── controller.py    orquestra o processamento das pastas (progresso/cancelar)
├── gui/                 INTERFACE (CustomTkinter)
│   ├── app.py           janela principal (cabeçalho + 4 abas); handler global de erros
│   ├── tab_processar.py aba 1 (PDF → planilha)
│   ├── tab_concatenar.py aba 2 (upload + novas faturas → concatena)
│   ├── columns_editor.py editor de colunas/abas
│   ├── tab_parametros.py aba 3: tabela de equivalências de itens (editável, persistida)
│   ├── tab_hardcodes.py aba 4: editor visual de regras SE→ENTÃO + aplicação sobre uma planilha
│   ├── mapping_dialog.py tela de mapeamento (quando não há metadados)
│   ├── widgets.py       SeletorPastas, SeletorLink, PainelProgresso
│   └── worker.py        processamento em thread + fila de eventos
└── resources/           glossario_itens.json (301 itens), correcoes.json, build_info.txt (carimbo)
                         (NÃO há dados de instituição: hardcodes e dicionário de UC são importados pelo usuário)
ferramentas/             vai para a raiz da pasta distribuída: processar.bat (rotina do modo CLI) e
                         gerar_powerquery.ps1 (Excel com uma consulta Power Query por CSV, via automação do Excel)
```

**Regra de ouro:** o `core/` nunca importa `gui/`. Toda a lógica de negócio é
testável sem abrir janela (ver `tests/`).

---

## 4. Fluxo de dados

### Processar (aba 1)
1. `controller.processar_jobs` percorre as pastas; para cada PDF chama
   `equatorial.processar_pdf` ou `chesp.processar_pdf`, que devolvem um dict com
   as linhas de cada aba base (`fatura`, `unidade_consumidora`, `itens_fatura`,
   `impostos`, `medicao`). Roda em **thread** (`gui/worker.py`); a GUI faz
   polling da fila.
2. `dataset.Dataset` acumula as linhas e, em `to_dataframes()`, monta os
   DataFrames **canônicos** e **deriva** `fatura_resumida` e `medicao_resumida`.
3. `links.aplicar_link` preenche `link_pdf`; `uc_map.aplicar` troca `id_uc` (se
   houver mapa).
4. `hardcodes.aplicar_dfs` aplica, **por último**, as regras SE→ENTÃO do usuário
   (aba 4) sobre os dados já completos.
5. `profile.Perfil.padrao_de_dataframes` cria o perfil (nomes = canônicos;
   colunas 100% vazias já desmarcadas). O usuário edita no `columns_editor`.
6. `glossario.garantir_glossario` acrescenta a aba glossario.
7. `excel_io.escrever_workbook` aplica o perfil, estiliza e grava, incluindo a
   aba oculta `_faturas_meta` (mapa nome_exibido → canônico).

### Concatenar (aba 2)
1. `excel_io.ler_workbook` lê a planilha base (+ metadados, se houver).
2. Processa as novas faturas (igual acima) → DataFrames canônicos.
3. Define o mapa nome_exibido→canônico de cada aba: dos **metadados** embutidos
   ou, se ausentes, por **auto-sugestão** + tela de mapeamento (`mapping_dialog`).
4. `concat.concatenar` traduz as novas faturas para o **layout da planilha
   enviada** (respeitando renomeações/exclusões) e empilha, com dedup.
5. `hardcodes.aplicar_dfs` (por último, sobre antigos + novos) + `uc_map.aplicar`
   (opcional) + `glossario.garantir_glossario` + salvar.

### Modo linha de comando (`cli.py`)

`FaturasDeEnergiaCLI.exe --cli --pasta <dir>[=FORNECEDOR] [--subpastas] --saida
<xlsx> [--csv <dir>] [--cache <dir>] [--paralelo N] [--mapa-uc <arq>]` (em
desenvolvimento: `python -m faturas_app --cli …`). Mesmo pós-processamento da
aba 1 (`cli.consolidar` = to_dataframes → links → derivados → hardcodes →
Perfil → glossário → excel_io), com:

- **Fornecedora por pasta**: depois do `=` ou inferida de qualquer pasta do
  caminho que contenha `chesp` / `equatorial`. Assim `--pasta acervo --subpastas`
  processa `acervo\equatorial\…` e `acervo\chesp\…` de uma vez.
- **Paralelismo**: `ProcessPoolExecutor` sobre `_processar_um` (função de módulo,
  picklável); `ex.map` preserva a ordem da listagem, então o lote entra no
  `Dataset` na mesma ordem da interface. O exe empacotado precisa do
  `multiprocessing.freeze_support()` no início de `__main__.main` (cada filho
  reexecuta o exe). 93 PDFs (50 CHESP, 10 por OCR) em ~50 s com 6 processos;
  o acervo inteiro (10,6 mil) em minutos, contra horas sequencial.
- **Cache** (`--cache`, padrão `<pasta da saída>\cache_faturas`): um JSON por
  PDF, chave = sha1(versão do app + caminho + tamanho + mtime). Rodar de novo só
  lê os PDFs novos/alterados; trocar a versão do app invalida tudo.
- **CSV por aba** (`--csv`): `;` e vírgula decimal (`df.to_csv(sep=";",
  decimal=",")`, UTF-8 com BOM) — o formato que o Excel pt-BR e o Power Query
  com cultura `pt-BR` leem sem configurar nada.
- **`--mapa-uc`**: importa o cadastro como a aba Parâmetros faria, sem
  perguntas (`cli.importar_mapa_uc`): chave `id_uc` ou o campo mais parecido,
  identificadores alternativos sugeridos todos marcados, itens do template por
  nome exato ou palavra-chave (`dicionario_uc.sugerir_mapeamento`) e os demais
  campos como colunas extras com nome normalizado (`_slug`). Grava no mesmo
  `%APPDATA%\FaturasEnergia\mapa_uc.json` da interface.
- Saídas: planilha, `<saida>_erros.txt` (se houver), `--log` opcional e um
  resumo (linhas por aba, contagem da `validacao`) no console.

`ferramentas/processar.bat` embrulha isso para a rotina mensal (pastas `..\pdfs`
→ `..\saida`) e chama `gerar_powerquery.ps1` na primeira vez para criar o Excel
com Power Query. O `.ps1` cria as consultas via COM (`Workbook.Queries.Add`, uma
por CSV, com `Table.TransformColumnTypes` por tipos detectados numa amostra do
CSV e a pasta num parâmetro `PastaCSV`) e tenta carregá-las em tabelas
(`Connections.Add2` + `ListObjects.Add`); se a carga falhar, as consultas ficam
como "somente conexão". **Só roda com Excel 2016+ instalado e ativado** — na
máquina de desenvolvimento a licença estava expirada e a automação foi recusada,
então a geração automática precisa ser validada na máquina do usuário; o
fallback documentado no LEIA-ME é criar as consultas pelo próprio Excel.
Fazer a extração inteira em Power Query/M não é viável (OCR, ~60 regexes,
cinco layouts).

### Hardcodes (aba 4)

Regras "SE → ENTÃO" **do usuário**, para consertar o que já veio errado na fatura
emitida pela concessionária (o processador leu certo; a origem é que está errada).
Não confundir com `correcoes.py`, que conserta erros de EXTRAÇÃO e é embutido no app.

- Estrutura: grupos de condições ligados entre si por **E**; dentro de cada grupo,
  as condições se ligam por **E** ou **OU** — expressando
  `SE (X=1 OU X=2) E (Y≠3) ENTÃO Z=0`. Grupos, condições e ações são incrementáveis.
- Persistidas em `%APPDATA%/FaturasEnergia/hardcodes.json`. Na primeira execução o
  arquivo começa VAZIO (o app não traz regra embutida); o arquivo do
  usuário manda (lista vazia é respeitada, não é re-semeada).
- Casamento **tolerante**, como em `correcoes.py`: nomes de aba/coluna e valores são
  normalizados (maiúsculas, sem acento, espaços colapsados) e a comparação é numérica
  quando os dois lados são números. Assim `Postos Horários` casa com `Postos horarios`
  e `quantidade = 30` casa com `"30"` e com `30.0`.
- Aplicados ao FINAL do processamento (abas 1 e 2) e, sob demanda, sobre uma planilha
  já pronta (`hardcodes.aplicar_planilha` → arquivo com sufixo `_hardcodes`).
- **Atenção:** a regra é escopada a UMA aba/coluna. Se a coluna alvo tiver derivados
  (`item` → `item_normalizado`; `medicao.Consumo kWh` → `medicao_resumida.energia_geracao_kwh`),
  acrescente a ação/regra correspondente — os hardcodes rodam DEPOIS de `derivados.py`
  e não são propagados automaticamente.

---

## 5. O design que resolve a re-concatenação (esquema canônico)

O ponto sensível: re-concatenar faturas novas a uma planilha que o usuário já
**renomeou ou teve colunas removidas**. Solução em camadas:

1. Os processadores sempre produzem **nomes canônicos** (`schema.CANONICAL_COLUMNS`).
2. Renomear/excluir é uma **camada de exibição** (`profile.Perfil`).
3. Ao salvar, grava-se a aba oculta **`_faturas_meta`** com o mapa
   `nome_exibido → canônico`. No reupload, esse mapa remapeia com exatidão.
4. Sem metadados, `concat.sugerir_mapeamento` adivinha por similaridade (+ apelidos
   em `schema.COLUMN_ALIASES`, ex.: `link_pdf`) e a `mapping_dialog` pede confirmação.
5. `concat.concatenar` usa o mapa para encaixar as novas faturas no layout do
   usuário e deduplica por `schema.DEDUP_KEYS` (ou linha completa em
   `schema.DEDUP_FULL_ROW`).

---

## 6. Pegadinhas / decisões importantes (LEIA antes de mexer)

- **`self._w` é reservado do Tkinter** (caminho da janela). NUNCA use `_w` como
  atributo em widgets CTk/Tk — usar quebra todo `grid()`/`grid_forget()`. Bug já
  ocorrido no editor (hoje usa `_widgets`).
- **App sem console**: exceções em callbacks somem. Há um **handler global**
  (`App._erro_inesperado`) que mostra aviso e grava `~/faturas_erro.log`.
- **Layout**: o rodapé (botão Salvar) é fixado com `pack(side="bottom")` para
  ficar sempre visível; o resto rola. Não voltar a empilhar tudo em `grid`.
- **OCR (Tesseract)**: ~22% das CHESP são escaneadas. O Tesseract conda-forge
  importa `libcurl.dll` que **não vem como dependência automática** — por isso
  `fetch_tesseract.ps1` instala `tesseract libcurl` juntos (senão o exe falha com
  `0xC0000135`). UB-Mannheim dá 403 a download automatizado.
- **Google Drive x build**: empacotar direto no `G:\` (Drive) causa corrida de
  I/O — o Drive move o `.exe` recém-escrito e o `os.chmod` do PyInstaller falha
  (`WinError 3`). Por isso `build.ps1` empacota em `%LOCALAPPDATA%\FaturasBuild`
  (disco local) e só grava os entregáveis (`.zip`, `setup.exe`) no Drive; o
  instalador lê o build local via `ISCC /DSrcDir=<local>`. **Rodar o setup.exe
  direto do Drive** também trava a instalação — copiar para o disco local antes.
- **Dedup só de linha 100% idêntica** para `itens_fatura`, `medicao` e
  `medicao_resumida` (`schema.DEDUP_FULL_ROW`): o mesmo conjunto-chave pode
  repetir no mês (variações de leitura); NÃO deduplicar por chave de colunas.
- **id_uc de faturas antigas** (`equatorial._extrair_id_uc`): fallbacks por época
  — Out/2023 pega a UC ao fim da linha de PERDAS; 2022-mai/2023 pega a UC antes
  de "NOTA FISCAL Nº".
- **`id_fatura` prefixado** propaga para TODAS as abas (itens, medição usam o
  mesmo `fid`). A busca do link usa `arquivo_pdf`/`numero_fatura`, não `id_fatura`.
- **Mapa de UCs: um registro, VÁRIOS identificadores.** O índice é por dígitos
  sobre todos os ids do registro (`id_uc` como lista ou `a; b`). Um cadastro em
  que a UC nova, a formatada e a velha vêm em COLUNAS separadas (`UC`,
  `id_uc`, `UC VELHA` — formato da planilha do TJGO) só casa as faturas
  antigas se essas colunas forem marcadas como "outros identificadores" na
  importação (`aplicar_mapeamento(..., ids_extras=[...])`); sem isso o mapa
  cobria 46 % das faturas. Linha com a chave vazia/`-` mas com identificador
  alternativo não é descartada (o alternativo vira o canônico). A coluna da
  Resolução ANEEL 1095/2024 (15 dígitos com zeros) NÃO é identificador
  alternativo: é o item `id_uc_aneel_bordero`.
- **Cadastro incompleto é silencioso sem a aba `validacao`**: a planilha do
  dicionário de 30/08/2026 tinha 103 UCs (subconjunto exato do JSON de 221 do
  Drive) e deixava 54 % das faturas sem `id_uc_canonico`. A regra
  `UC_FORA_DO_MAPA` existe para isso aparecer.
- **PDFs direto do Google Drive (`J:`) custam ~1 s cada** (streaming) — 10,4 mil
  faturas ≈ 4 h sequencial. Copiar o acervo para disco local (`robocopy /MT:16`,
  ~11 min para 8,4 GB) e rodar o CLI em paralelo leva minutos.

### Casos de parsing conhecidos (Equatorial, `equatorial.py`)
- **Texto EMBARALHADO do layout 2022** (tabela de medição e de itens lado a
  lado): quando linhas das duas caem na mesma altura o pdfplumber intercala os
  caracteres (`1 1 1 1 6 6 3 3 8 8 …`) e a linha de medição se perde
  (2022038476622 saía com 9 das 16 linhas). `_montar_resultado` detecta a
  assinatura (`_RE_TEXTO_EMBARALHADO`: 12+ tokens de 1 caractere) e reextrai a
  medição só da **coluna da esquerda** da página (`extrair_texto_recortado`:
  `page.crop` até o x do cabeçalho `Itens`), ficando com o que rendeu mais
  linhas. Só em PDF de fatura única (`numero_forcado is None`). `dedupe_chars`
  do pdfplumber NÃO resolve: com tolerância alta ele também come dígitos
  repetidos legítimos (`997038` → `97038`).
- **UC sem contrato de demanda** (`CONSUMO/DEMANDA S/ CONTRATO`): caixa
  "Grandezas Contratadas" vazia ⇒ `demanda_contratada_kw = 0`, não nulo.
- **Leitura Anterior opcional** na medição: linha com 1 só inteiro (célula vazia
  no PDF) não é perdida (`pat_a` com grupo opcional).
- **Medidor COLADO na grandeza** (`12794856-2ENERGIA ATIVA - KWH ÚNICO …`): no
  template usado até meados de 2023, nas faturas de baixa tensão (posto ÚNICO),
  as duas colunas saem sem espaço entre elas. Os padrões com o medidor à
  esquerda usam `SEP = {H}*` (espaço opcional) por causa disso — era o motivo
  de ~1.000 faturas de 2022–mai/2023 ficarem com a aba `medicao` vazia.
- **Linha truncada com o medidor à direita** (`ENERGIA ATIVA - KWH PONTA 086926
  0,012000 11556447-1`): falta uma das colunas de leitura e a de "Consumo" —
  capturada pelo `pat_e`, que exige o medidor no formato com hífen (`\d+-\d+`,
  como a Equatorial sempre imprime) para não confundi-lo com um consumo solto.
- **Em QUAL coluna fica a leitura de uma linha truncada** (`pat_c`/`pat_e`): o
  texto achatado do pdfplumber **não** permite saber — `… ÚNICO 000000 50,000000`
  é idêntica tendo faltado a coluna da esquerda ou a da direita, e as duas coisas
  ocorrem no acervo (medido nas 31 faturas com linha truncada: 78 linhas em que
  falta a "Atual", 6 em que falta a "Anterior"). Por isso
  `_resolver_coluna_leitura` **relê o PDF pelas coordenadas** e compara o x da
  leitura com o das colunas, ancorando (1) nas linhas completas da própria
  fatura ou (2) na tabela `_GRADE_MEDICAO` (x da constante → x das leituras,
  medida em ~4.400 linhas completas). Só roda quando há linha truncada (~38 de
  10.214 faturas) e, se o PDF não abrir (escaneado/OCR), mantém o padrão
  "Anterior". Chutar sempre a mesma coluna era o que gerava a linha impossível
  **"Leitura Atual > Leitura Anterior com Consumo zero"**.

### Casos de parsing conhecidos (CHESP, `chesp.py`)
- **"Único" corrompido** (`?nico`, `¿ico`, `Ãšnico`): a fonte do PDF não traz o
  caractere acentuado. O `POSTO` aceita qualquer token curto terminado em `ico`
  e `_padronizar_medicao_chesp` normaliza para `ÚNICO`.
- **`Energia Reativa-kVArh`**: alternativa mais longa que `Energia Reativa`,
  precisa vir antes na alternância; normalizada para `ENERGIA REATIVA - KWH`.
- **Dois layouts antigos (2022)** em `_medicao_layouts_antigos`: "Modelo 6"
  (`ATIVA kWh 56475,000 …`, sem coluna de posto) e "Grupo A" (`kWh Ativa F P
  10.549,471 …`, rótulo juntando grandeza e posto). Nos dois o nº do medidor
  vem do cabeçalho (`Nº MEDIDOR: …`), não da linha. Só rodam **quando o padrão
  atual não devolveu nenhuma linha** — assim nenhuma fatura que já era extraída
  corretamente muda de resultado.
- **RELIGAÇÃO/DESLIGAMENTO PROGRAMADO**: itens financeiros COM quantidade
  (nome+qtd+preço+valor) — tratados no padrão `mem` junto de EMIS. SEGUNDA VIA.
- **DEMANDA ISENTO DE ICMS**: às vezes alíquota `0` sem `%` e sem coluna ICMS (7
  tokens) — padrão dedicado `m_isento` (senão a tarifa recebia a base).
- **SCEE `SALDO KWH`**: 3 formatos — número único; `ATV:`/`ATV=` (equivale ao
  total); por posto `P=.., FP=.., HR=..`. A captura usa **DOTALL** porque o bloco
  pode quebrar em duas linhas (HR embaixo).
- **`data_emissao` com o rótulo quebrado**: `… SÉRIE 000 / DATA DE` numa linha
  e `CPF/CNPJ: … EMISSÃO: 16/01/2025` na seguinte, com texto de outra coluna no
  meio — em 193 das 203 faturas (texto ou OCR). O regex original exigia os dois
  pedaços colados; hoje há dois fallbacks (`DATA DE[^\n]{0,60}\n[^\n]{0,80}?EMISSÃO:`
  e `EMISSÃO:` solto) e, no Modelo 6, a 4ª data da linha `ANTERIOR ATUAL
  PRÓXIMA EMISSÃO APRESENTAÇÃO`.
- **Medição escaneada com zero lido como "o"** (`Demanda-kW Ponta o o 100 23`):
  parte das linhas casa o padrão normal e o resto se perdia (24 faturas A4 com
  3–5 das 9 linhas). `_medicao_ocr_tolerante` agora também roda como
  **complemento** quando o layout atual rendeu linhas — acrescenta só as
  (grandeza, posto) ausentes, nunca reescreve o que já foi lido; num PDF de
  texto tudo já casou e nada muda.

---

## 7. Como fazer alterações comuns

**Adicionar uma coluna nova a uma aba:**
1. Extraí-la no processador (`equatorial.py`/`chesp.py`), adicionando a chave no
   dict retornado por `extrair_fatura`/`extrair_itens...`.
2. Registrar o nome canônico em `schema.CANONICAL_COLUMNS[<aba>]` (na ordem
   desejada). Se puder vir vazia mas deve sempre aparecer, adicionar a
   `schema.COLS_PROTEGIDAS`.
3. (Opcional) documentar em `glossario.COLUNAS_DOC`.

**Adicionar uma aba derivada** (como as resumidas): definir suas colunas em
`schema.CANONICAL_COLUMNS`, incluí-la em `schema.SHEET_ORDER` e `DERIVED_SHEETS`,
dar cor em `SHEET_COLORS`, definir dedup (`DEDUP_KEYS` ou `DEDUP_FULL_ROW`) e
implementar a derivação em `dataset.Dataset.to_dataframes` — ou, se ela depende
do lote inteiro/do mapa de UCs (como `tarifas` e `validacao`), em
`derivados._calcular` + `derivados.ABAS_RECALCULADAS` (reinstalada inteira na
concatenação).

**Adicionar uma regra de validação:** um `add(i, gravidade, regra, detalhe)` no
laço de `derivados._derivar_validacao` e a descrição em
`glossario.REGRAS_VALIDACAO_DOC` (+ teste em `tests/test_ajustes_set2026.py`).

**Adicionar uma distribuidora nova:** criar `core/<nova>.py` com
`processar_pdf(path) -> {aba: linhas}` (mesmas abas base), registrar em
`controller.PROCESSADORES` e em `gui/widgets.FORNECEDORES`.

**Mudar o glossário:** editar `core/glossario.py` (docs/conceitos) ou regenerar
`resources/glossario_itens.json` a partir do PDF oficial (parse por coordenadas
de coluna, corte em x=270).

---

## 8. Build e distribuição

Pré-requisitos: Windows + Python 3.12 + internet (1ª vez baixa o Tesseract).
Tudo num `.venv` isolado.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-build.txt
powershell -ExecutionPolicy Bypass -File build\fetch_tesseract.ps1   # 1x: monta tesseract/
powershell -ExecutionPolicy Bypass -File build\build_tudo.ps1        # gera zip + setup.exe
```

`build/build_tudo.ps1` orquestra: provisiona o que faltar (tesseract, ícone, Inno
Setup via winget) → PyInstaller (`build/faturas.spec`) → `.zip` → instalador
(`build/installer.iss`). Grava o carimbo de atualização (`build.ps1` escreve
`resources/build_info.txt`). Saída: `dist/FaturasDeEnergia.zip` (~100 MB) e
`dist/FaturasDeEnergia-Setup.exe` (~72 MB).

O spec gera **dois executáveis** na mesma pasta (`COLLECT(exe, exe_cli, …)`):
`FaturasDeEnergia.exe` (janela, `console=False`) e `FaturasDeEnergiaCLI.exe`
(`console=True`, para o modo linha de comando mostrar progresso e erros). Os
dois compartilham `_internal/`. `build.ps1` copia `ferramentas/*` (`processar.bat`,
`gerar_powerquery.ps1`) e o `LEIA-ME.txt` para a raiz da pasta distribuída.

**Validar o `.exe`:** rodar com `FATURAS_SELFCHECK=<arquivo>` no ambiente — o app
grava um relatório (imports, OCR, glossário) e sai sem abrir a janela. Truque:
a contagem de termos do glossário no relatório muda quando o código muda, então
serve para confirmar que o pacote tem a versão nova.

---

## 9. Testes

- `tests/` — 130 testes sem PDFs (trechos reais de texto): concatenação,
  hardcodes, medição (Equatorial/CHESP, recuperadas e truncadas), demanda
  contratada, mapa de UCs, tarifas, borderôs, importação inteligente e
  `test_ajustes_set2026.py` (demanda "S/ CONTRATO", mensagens, `data_emissao`
  CHESP, OCR, aba `validacao`, chave/alternativos do mapa, CLI).
  Rodar: `PYTHONPATH=src .venv\Scripts\python.exe -m pytest tests -q`.
- **Conjunto rápido**: `testes_exec/conjunto_faturas/{eq,chesp}` (66 EQ) — cobre
  os formatos SCEE (plano, ATV, por posto) e casos de parsing. Usar para iterar
  rápido em vez das pastas grandes (`pdfs/energia_tjgo/equatorial/*`).
- **Reconciliação**: para validar a extração de itens, soma de `valor_r$` por
  `id_fatura` ≈ `valor_total_r$` (tolerância R$ 1). Faturas com créditos/
  compensações não itemizados não fecham (herdado dos notebooks originais).

---

## 10. Limitações conhecidas

- Windows-only; `.exe` não assinado (SmartScreen pede "Executar assim mesmo").
- `caminho_pdf` é caminho local (não abre em outra máquina); `link_pdf` de busca
  no Drive é aproximado. Link **exato** por arquivo exigiria a API do Drive
  (OAuth) — não implementado para manter o app sem configuração.
- OCR de faturas muito degradadas pode falhar em campos; erros aparecem no log e
  as demais faturas seguem.
