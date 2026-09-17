# Como o extrator funciona — documentação técnica completa (v4.0)

Esta documentação explica, arquivo por arquivo, como o **Processador de Faturas de Energia e Água** transforma PDFs em
dados estruturados, e compara o que o **aplicativo desktop** e o **bot do Telegram @doc_gEEstor_bot** fazem com esse
mesmo núcleo. Complementa o [README](../README.md) (visão geral e build), o [manual de uso](MANUAL_DE_USO.md)
(passo a passo com capturas de tela) e, no projeto da VM, `DOCUMENTACAO_COMPLETA_GEESTOR.md` (bancos, bot, servidor).

Sumário

1. [Ideia central: um núcleo, duas superfícies](#1-ideia-central-um-núcleo-duas-superfícies)
2. [Mapa dos arquivos](#2-mapa-dos-arquivos)
3. [Energia — faturas individuais (Equatorial / CHESP)](#3-energia--faturas-individuais-equatorial--chesp)
4. [Energia — borderôs (faturas agrupadas)](#4-energia--borderôs-faturas-agrupadas)
5. [Água — todas as concessionárias no mesmo modelo](#5-água--todas-as-concessionárias-no-mesmo-modelo)
6. [Cache, paralelismo e linha de comando](#6-cache-paralelismo-e-linha-de-comando)
7. [O bot: o mesmo extrator dentro da VM](#7-o-bot-o-mesmo-extrator-dentro-da-vm)
8. [Aplicativo desktop × bot — comparação de funcionalidades](#8-aplicativo-desktop--bot--comparação-de-funcionalidades)
9. [Testes, build e publicação](#9-testes-build-e-publicação)
10. [Limitações conhecidas](#10-limitações-conhecidas)

---

## 1. Ideia central: um núcleo, duas superfícies

Todo o conhecimento sobre os PDFs está no pacote Python `faturas_app` (pasta `src/`). Ele **não depende de interface**:
recebe caminhos de PDF e devolve linhas em **colunas canônicas** (nomes fixos, definidos em `core/schema.py` para energia
e `core/agua/schema_agua.py` para água). Sobre esse núcleo há duas superfícies:

* o **aplicativo desktop** (`gui/`, CustomTkinter), empacotado com PyInstaller — roda na máquina do usuário e grava
  planilhas Excel;
* a **linha de comando** (`cli.py`, `python -m faturas_app --cli …`), que é exatamente o que o **bot** chama na VM para
  processar cada lote; o bot então grava as mesmas linhas nas tabelas do PostgreSQL.

Consequência prática: um PDF lido no desktop e o mesmo PDF lido pelo bot produzem **as mesmas colunas e os mesmos
valores**; o que muda é o destino (planilha × banco) e o que se faz depois (editar colunas × consultar/aprovar/auditar).

```
PDF ──► extrator (faturas_app.core) ──► linhas canônicas ──┬──► planilha Excel (desktop / CLI)
                                                            └──► tabelas_* no PostgreSQL (bot, carga inicial)
```

## 2. Mapa dos arquivos

```
src/faturas_app/
├── __init__.py              __version__ (4.0.0) e APP_NAME
├── __main__.py              entrada: GUI, --cli, e autoverificação do exe (FATURAS_SELFCHECK)
├── cli.py                   modo linha de comando: energia (--pasta) e água (--agua), cache, paralelo, CSV, log
├── core/
│   ├── schema.py            colunas CANÔNICAS de energia por aba, apelidos, chaves de dedup, cores das abas
│   ├── equatorial.py        extrator de faturas Equatorial/ENEL (texto do PDF + regex por bloco)
│   ├── chesp.py             extrator de faturas CHESP (texto ou OCR)
│   ├── ocr.py               localização do Tesseract (embutido em tesseract/ ou do sistema) e OCR de página
│   ├── borderos.py          borderôs de energia (Equatorial/ENEL): âncoras posicionais, OCR, conferência soma × total
│   ├── dataset.py           acumula as linhas canônicas e monta os DataFrames das abas (+ abas derivadas)
│   ├── derivados.py         colunas derivadas de energia (tarifas, ids canônicos) e validação
│   ├── dicionario_uc.py     mapa de UCs (dicionário) em %APPDATA%\FaturasEnergia
│   ├── hardcodes.py         regras SE → ENTÃO aplicadas na saída
│   ├── equivalencias.py     item impresso → item normalizado
│   ├── profile.py           camada de exibição (renomear/ocultar colunas e abas) e metadados da planilha
│   ├── excel_io.py          escrita estilizada do .xlsx + aba oculta de metadados; leitura
│   ├── concat.py            "Adicionar a uma planilha": remapeia para o layout da base e deduplica
│   ├── controller.py        orquestra pastas/jobs, progresso e cancelamento (energia)
│   ├── glossario.py         aba glossario (energia)
│   ├── links.py             coluna link_pdf (busca no Drive / caminho local / modelo de URL)
│   ├── correcoes.py, build_info.py, dicionario_uc.py …
│   ├── atualizacao.py       ATUALIZAÇÃO OBRIGATÓRIA: consulta a última release no GitHub
│   └── agua/                ÁGUA (v4.0) — ver seção 5
│       ├── schema_agua.py   fornecedores (CNPJ), abas, colunas canônicas, chaves, categorias de valor
│       ├── texto.py         Documento: texto em LAYOUT de colunas por página (PyMuPDF) + OCR posicional; utilidades
│       ├── identificar.py   concessionária (CNPJ → palavras-chave → nome do arquivo) e tipo (fatura/borderô/analítica)
│       ├── base.py          regex tolerante a espaçamento, montagem/fechamento das linhas, itens, histórico, Resultado
│       ├── saneago_bordero.py     borderô da Saneago (formatos antigo e novo, várias faturas por PDF, OCR)
│       ├── saneago_analitica.py   fatura analítica da Saneago (um bloco por conta)
│       ├── gsan.py          família GSAN: Ipameri, Buriti Alegre, São Simão, SAE Catalão (+ modelo "nota fiscal" da SSSA)
│       ├── demae.py         DEMAE Caldas Novas (texto) e DEMAE Panamá (OCR parcial)
│       ├── duam.py          DUAM: SAAE Corumbá (2021–2025 e 2026) e SAAE Mineiros (texto e OCR 2026)
│       ├── saae_abadiania.py, sanesc.py, leopoldo_bulhoes.py, codego.py
│       ├── extrator.py      despacho: Documento → identificar → extrator da família → Resultado
│       ├── mapa_conta.py    mapa de contas (JSON em %APPDATA%): importação, construção automática, conta canônica
│       ├── derivados_agua.py  conta canônica/unidade pelo mapa, VALIDAÇÃO, cruzamento borderô × analítica
│       ├── controller_agua.py lote: listar, cache, paralelo, dedup, DataFrames, planilha, concatenação
│       └── glossario_agua.py  aba glossario da água
└── gui/
    ├── app.py               janela: domínios Energia Elétrica / Água; verificação de atualização em segundo plano
    ├── tab_processar.py, tab_concatenar.py, tab_parametros.py, tab_hardcodes.py   energia
    ├── tab_borderos.py, tab_borderos_concatenar.py                                 borderôs
    ├── tab_agua.py          Água: processar / adicionar a uma planilha / mapa de contas
    ├── widgets.py           seletor de pastas, painel de progresso, seletor de link
    ├── columns_editor.py, mapping_dialog.py, editor_json.py, mapa_uc_dialog.py, dialog_erros.py, worker.py
tests/                       pytest (147 testes; test_agua.py cobre a água com páginas sintéticas)
build/                       PyInstaller (faturas.spec, build.ps1), instalador Inno Setup, Tesseract portátil
docs/                        este documento, o manual de uso e as capturas de tela
```

## 3. Energia — faturas individuais (Equatorial / CHESP)

1. **Entrada** (`core/controller.py`): cada pasta vem com a fornecedora (EQUATORIAL ou CHESP); `listar_pdfs` percorre as
   subpastas quando pedido; `processar_jobs` chama o processador certo por PDF, com progresso e cancelamento.
2. **Equatorial** (`core/equatorial.py`): o texto da fatura é lido com `pdfplumber`/PyMuPDF; cada bloco da fatura
   (identificação, itens faturados, tributos, medição, informações do SCEE, mensagens) é localizado por âncoras e lido com
   expressões regulares; a UC, o número da fatura, competência, datas, valores, classificação tarifária, demanda
   contratada e os saldos do SCEE saem para a aba `fatura`; os itens para `itens_fatura` (com `tipo`, quantidade,
   preço, PIS/COFINS, ICMS); tributos para `impostos`; leituras/consumos por grandeza e posto horário para `medicao`.
3. **CHESP** (`core/chesp.py`): mesmo esquema de saída, com layout próprio; quando a página não tem texto (fatura
   digitalizada), `core/ocr.py` renderiza a página e passa pelo **Tesseract** embutido.
4. **Dataset** (`core/dataset.py`): acumula as linhas; monta os DataFrames das abas base e das derivadas
   (`fatura_resumida`, `medicao_resumida`).
5. **Derivados e validação** (`core/derivados.py`): `id_uc_canonico` (pelo mapa de UCs, `dicionario_uc.py`), tabela
   `tarifas` (primeira competência de cada combinação fornecedor + item + tarifa), regras de validação
   (`ITENS_NAO_FECHAM`, `DEMANDA_AUSENTE_UC_AT`, `UC_FORA_DO_MAPA`…), `equivalencias` de itens e `hardcodes` do usuário.
6. **Saída** (`core/profile.py` + `core/excel_io.py`): a camada de exibição renomeia/oculta colunas conforme o perfil
   do usuário; a planilha leva uma aba oculta `_faturas_meta` com o mapa exibido → canônico, que é o que permite
   **adicionar faturas novas** a uma planilha já editada (`core/concat.py`).

Identificação: `id_fatura = <FORNECEDORA>_<número da fatura>` liga todas as abas; `numero_fatura` guarda o número
original (na Equatorial é o nome do PDF no Drive, o que faz o `link_pdf` de busca funcionar).

## 4. Energia — borderôs (faturas agrupadas)

`core/borderos.py` lê o borderô da Equatorial/ENEL (várias UCs num único documento):

* **identidade** vem do conteúdo (número da fatura agrupada, código de agrupamento, competência, vencimento); o nome do
  arquivo é só o último recurso;
* **cabeçalho**: total, quantidade de contas, bruto e retenções (âncoras de texto);
* **unidades**: as palavras posicionais de cada página (`page.get_text("words")`) são agrupadas em linhas por `y`
  (`_clusterizar_linhas`) e cada linha com uma UC (inclusive dígito verificador `X`) vira uma linha da aba `unidades`
  (valor bruto, COFINS, PIS, IRRF, CSLL, valor líquido); páginas-imagem passam por OCR posicional (`_ocr_palavras`);
* **resumo dos valores cobrados**: grade CÓDIGO / DESCRIÇÃO / VALOR → aba `resumo_valores`;
* **conferência**: `bate_total` = a soma das UCs extraídas confere com o total impresso (tolerância R$ 1); borderôs
  digitalizados sem UC legível ficam com `escaneado = SIM` e `bate_total = N/A`.

`escrever_dfs`/`ler_planilha`/`concatenar` fazem a planilha de borderôs e o "Adicionar a uma planilha".

## 5. Água — todas as concessionárias no mesmo modelo

### 5.1 Princípio

Doze concessionárias, doze layouts — mas **um único esquema de saída**. Cada extrator devolve dicionários com as colunas
de `schema_agua.py`; o que uma concessionária não imprime fica vazio. Assim SAE Catalão, DEMAEs, SAAEs, SANESC, São
Simão, Ipameri, Buriti Alegre, CODEGO e a Saneago (borderô e analítica) convivem nas mesmas abas da planilha e nas
mesmas tabelas do banco, diferenciadas pela coluna `fornecedor`.

Abas/tabelas: `fatura_agua` (uma linha por fatura individual **ou** por conta da analítica da Saneago), `itens_agua`,
`historico_agua`, `borderos_agua`, `contas_bordero_agua`, `validacao_agua`, `mapa_contas_agua`.

### 5.2 O texto em layout (`core/agua/texto.py`)

Diferente da energia, os extratores de água **não** usam o texto corrido nem `pdftotext`: a classe `Documento` monta,
para cada página, um **texto em layout de colunas** a partir das palavras posicionais do PyMuPDF — cada palavra é
colocada na coluna de caractere correspondente ao seu `x` (largura de caractere = mediana da página), e as palavras são
agrupadas em linhas por `y`. O resultado é um texto em que os rótulos e os valores de uma tabela ficam alinhados, o que
permite ler colunas pela posição e blocos pela proximidade, com regex simples.

Detalhes que fizeram diferença no acervo real:

* **Rótulos com vários espaços** — como o layout é proporcional, "QUANTIDADE DE CONTAS AGRUPADAS" vira
  "QUANTIDADE    DE CONTAS   AGRUPADAS"; por isso todas as expressões usam `\s+` entre palavras (`base.rx`) e os
  testes de substring são feitos sobre o texto com os espaços colapsados.
* **Páginas rotacionadas** — a SAAE Abadiânia (2022+) grava a página com rotação de 180° e a SANESC 2022 desenha o
  texto "em pé" sem marcar `/Rotate`: `_matriz_orientacao()` combina `page.rotation_matrix` com a direção das linhas do
  PyMuPDF (`dir`) e leva as palavras ao espaço exibido antes de montar o layout.
* **Texto embutido inútil** — PDFs com fonte simbólica (SAAE Mineiros 2026), só com glifos invisíveis (Saneago 2021)
  ou com camada de texto de scanner ruim (borderôs Saneago de mai/set 2025: "14477239" no lugar de "144.772,39")
  parecem ter texto mas não têm: `texto_ilegivel()` detecta (poucos caracteres alfanuméricos, proporção de símbolos,
  nenhuma palavra do vocabulário de faturas, tabela de valores sem vírgulas) e manda a página para o **OCR**.
* **O nome do arquivo socorre o OCR** — o acervo nomeia os PDFs com número, mês e vencimento ("FATURA Nº 185278 - …
  - JANEIRO.2025 - VENC. 24.02.2025.pdf"); quando a página é digitalizada, `numero_do_nome`, `competencia_por_caminho`
  (mês do nome + ano da pasta) e `vencimento_do_nome` prevalecem sobre o que o OCR leu.
* **OCR posicional** — reutiliza `borderos._ocr_palavras` (Tesseract com caixas de palavras); o layout resultante é
  tratado pelos mesmos extratores, com tolerâncias a erros típicos (dígito verificador colado, vírgula perdida em
  valores, `O`/`0`).
* `data_iso`, `moeda`, `competencia` (aceita `04/2024`, `MAR/2021`, `Janeiro/2026`, `2024-04`), `competencia_do_nome`
  (do nome do arquivo do acervo), `categoria_valor` (agua / esgoto / taxas / multa_juros / credito / outros).

### 5.3 Identificação (`core/agua/identificar.py`)

Ordem: **CNPJ impresso** (tabela `FORNECEDORES`) → palavras-chave do texto (razão social, cidade) → dicas do nome do
arquivo e da pasta (para PDFs digitalizados sem texto). O tipo, só relevante na Saneago: `analitica_agua` ("FATURA
ANALÍTICA DE ÓRGÃO PÚBLICO"), `bordero_agua` ("ÓRGÃO AGRUPADOR", "CONTAS AGRUPADAS", cabeçalho "CONTA - DV"), senão
`fatura_agua`.

### 5.4 Os extratores, por família

| Módulo | Concessionárias | Como lê |
|---|---|---|
| `saneago_bordero.py` | Saneago — borderô | Percorre as páginas: `Nº FATURA` abre uma fatura (um PDF traz até 3); o cabeçalho da tabela (`CONTA - DV NOME CLIENTE LOGRADOURO …`) dá as **posições das colunas**; cada linha de conta é lida da direita para a esquerda (valores → consumo → texto) e cada número vai para a coluna cujo rótulo está mais perto (uma coluna em branco não desloca as outras — o mesmo princípio do extrator original de Matheus Braga). Dois formatos: antigo (CONSUMO ÁGUA · VALOR · CONSUMO ESGOTO · VALOR) e novo (CONSUMO · ÁGUA · ESGOTO · SMRSU). O logradouro é separado do nome pela coluna estimada na própria página. Rodapé: totais por coluna, `BASE DE CÁLCULO`, alíquota, `IMPOSTO RETIDO`, `VALOR FINAL DA FATURA`, `QUANTIDADE DE CONTAS AGRUPADAS` (valores na linha vizinha a partir de 2026); comunicado com `VALOR TOTAL EM R$`. `bate_total` compara a soma das contas com o total impresso. |
| `saneago_analitica.py` | Saneago — analítica | Cada bloco `CONTA N°: xxxx-d` vira uma linha de `fatura_agua` (`origem = analitica`): nome, endereço, hidrômetro, tipo de consumo, leituras/datas (formato 2024+) ou só consumo (2021–2023), lançamentos (`101 - TARIFA AGUA - RESIDENCIAL … 270,65`) com código, `VALOR TOTAL (R$)`, histórico de 6 meses (m³ e R$). A referência vale a última `REFERÊNCIA:` vista antes do bloco (arquivos com mais de um órgão pagador). |
| `gsan.py` | Ipameri, Buriti Alegre, São Simão, SAE Catalão | Canhoto `FATURA: MM/AAAA Nº n VENCIMENTO: d VALOR (R$): v`, `MATRÍCULA: m DÍGITO: d`, `HIDRÔMETRO N.º`, leituras/datas, dias, ocorrência; itens na **coluna da direita** a partir de `DESCRIÇÃO DOS ITENS FATURADOS` até `TOTAL A PAGAR` (linhas `> …` de detalhe ignoradas); histórico `MM/AAAA Lido leitura lido faturado`; categoria pela contagem `RES COM PÚB IND`. São Simão 2022–2024/2026 usa o modelo "Nota Fiscal Fatura" (`Id:`, `MATRÍCULA: n-d`, `Leitura ant. / Leitura atual / Consumo real / Consumo fat.`), tratado em `_nota_fiscal`. |
| `demae.py` | DEMAE Caldas Novas, DEMAE Panamá | Caldas Novas: `Matrícula:`, `Fatura nº:`, `Referência:`, `Data de Vencimento:`, `Valor: R$`, `MORADOR:`, itens à direita, histórico com as linhas `(Anterior)` / `(Atual)` dando leituras e datas. Panamá: acervo 100 % digitalizado — extração **parcial** por OCR: número da guia (AA MM + ligação, ex. 240123382 → 2024-01, conta 23382), vencimento (do nome do arquivo), valor (`VALOR À PAGAR`, com a vírgula perdida reconstruída), hidrômetro. |
| `duam.py` | SAAE Corumbá, SAAE Mineiros | DUAM (Documento Único de Arrecadação Municipal): `N. Duam`, `Referência: m / aaaa`, `Nº Conta`, `Nº hidrometro`, leituras do mês/anterior, consumo, `Vencimento:` com a data na linha de baixo, `(-) Valor do Pagamento` → `R$ v`, receitas `código descrição valor` (`178 TARIFA BASICO OPERACIONAL 8,00`, `30 TARIFA DE AGUA 248,22`; Mineiros: 1146/142/143). Corumbá 2026 tem layout novo (`N. Duam Referência Parcela Categoria Hidrômetro`, `CCI ID Fatura Leitura Atual …`, `Composição do Valor`). Mineiros 2026 é imagem: ramo OCR (`_ocr`) lê conta, referência, vencimento, leituras, itens e total. |
| `saae_abadiania.py` | SAAE Abadiânia | Canhoto `0001255.2 FEV/2024 240003278 23/02/2024 102,60` (inscrição, mês de faturamento, NF/conta, vencimento, valor); itens `001 TARIFA DE AGUA(…) 68,40` e `TARIFA DE AGUA (000 a 0010 - …) 70,90` (faixas, 2025+); linha de hidrometria (hidrômetro, instalação, leituras, datas, consumo, dias); últimos consumos `FEV/24 03 000 29`. 2021 é digitalizado: ramo OCR parcial. A competência é o **MÊS FAT.** impresso (mês de faturamento). |
| `sanesc.py` | SANESC (Senador Canedo) | Três modelos: **2021** = guia igual à de Leopoldo de Bulhões (`Número da guia`, `CÓD. LIG.: 07155-5`, `MÊS / ANO`) → mesmo extrator, com o cadastro sem o DV para a conta canônica coincidir (7155); **2022+** = linha `cadastro código-de-baixa hidrômetro ref vencimento`, leituras (`economias dias data leit_ant leit_atual consumo cons_fat`), `Categoria`, receitas `AGUA 929,74` / `ESGOTO 743,79` no fim das linhas do histórico, `TOTAL DA CONTA:`, histórico `m/aaaa consumo leitura dias data`; **boletim de arrecadação** (2ª via de cobrança) = `Dívida Cadastro Vencimento … Valor`, `Total da Guia`, receitas `Cód Receita Valor`. Sem número de fatura: `id = SANESC_<cadastro>_<AAAA-MM>`. |
| `leopoldo_bulhoes.py` | SAAE Leopoldo de Bulhões | `Número da guia` (`01851032024-7`), `CÓD. LIG.`, `MÊS / ANO` (`Janeiro/2026`), itens `TARIFA DE ÁGUA R$ 82,55` / `CUSTO MINIMO FIXO`, linha de datas (`leitura anterior · leitura · próx. · [emissão original] · vencimento · R$ valor`), leituras em m³, hidrômetro, histórico de 12 meses. Guias de 2024 têm camada de texto de scanner (rótulos e valores em linhas separadas): os itens são pareados na ordem. |
| `codego.py` | CODEGO | porte do extrator original; sem PDF no acervo para validar (marcado experimental). |

Todos passam por `base.fechar_fatura`: conta em dígitos (com o DV), competência (do nome do arquivo se faltar), datas em
ISO, `id_fatura_agua`, somas por categoria a partir dos itens (`valor_agua`, `valor_esgoto`, `valor_taxas`,
`valor_multa_juros`) e `soma_itens`; quando o PDF foi lido por OCR e o nome do arquivo traz `FATURA Nº n`, o número do
arquivo prevalece sobre o do OCR.

### 5.5 Mapa de contas, derivados e validação

* `mapa_conta.py` — JSON em `%APPDATA%\FaturasEnergia\mapa_contas_agua.json`; chave = dígitos da conta sem zeros à
  esquerda dentro do fornecedor; `importar()` lê o `contas.json` do projeto original (CONTA_DV, CONTA, UNIDADE,
  ENDERECO, DISTRIBUIDORA, OPERANTE, AGUA, ESGOTO, SMRSU) ou uma planilha; `construir_de_extracao()` monta o mapa a
  partir das faturas (um registro por fornecedor + conta, consolidando nome, endereço, hidrômetro, serviços e
  competências) — foi assim que o mapa do acervo do TJGO foi gerado, já que o `contas.json` real não estava disponível.
* `derivados_agua.py` — `conta_canonica` / `unidade_institucional` em todas as linhas (uma fatura digitalizada sem
  conta legível herda a conta do mapa quando a concessionária tem **uma única conta** cadastrada — Buriti Alegre,
  Leopoldo de Bulhões, SANESC, Corumbá, Abadiânia, DEMAE Panamá —, com a ocorrência `CONTA_INFERIDA_PELO_MAPA`);
  regras de validação (uma linha por ocorrência): `CONTA_AUSENTE`, `COMPETENCIA_AUSENTE`, `VALOR_TOTAL_AUSENTE`,
  `ITENS_NAO_FECHAM` (soma dos itens × total, tolerância R$ 1), `FATURA_SEM_NUMERO`, `LIDA_POR_OCR`, `LEITURA_INCONSISTENTE`, `CONSUMO_DIVERGENTE`,
  `VENCIMENTO_ANTES_DA_COMPETENCIA`, `CONTA_FORA_DO_MAPA`, `DUPLICIDADE`, `BORDERO_NAO_CONFERE`, `BORDERO_ESCANEADO`,
  `BORDERO_CONTAS_DIFEREM`; e o **cruzamento borderô × analítica** da Saneago (`ANALITICA_DIVERGE_BORDERO`,
  `CONTA_SEM_ANALITICA`, `CONTA_SEM_BORDERO`) — a mesma conta, na mesma competência, deve ter o mesmo valor bruto nos
  dois documentos.
* No banco (VM) a mesma validação existe em SQL (`derivados_agua.validacao`), sempre atualizada.

### 5.6 Lote, cache e planilha (`controller_agua.py`)

`processar_pastas()` lista os PDFs, processa em paralelo (threads — o OCR roda num processo externo), guarda um JSON
por PDF no cache (chave = versão do extrator + caminho + tamanho + data), deduplica por `id_fatura_agua` /
`id_bordero_agua` (registrando `DUPLICIDADE`), preenche `link_pdf`, aplica o mapa e a validação e devolve um
`ResultadoLote` com o resumo. `dataframes()` monta as abas (colunas canônicas, numéricas convertidas),
`escrever_planilha()` grava o `.xlsx` estilizado com o glossário, `ler_planilha()` / `divergencias()` / `concatenar()`
sustentam o "Adicionar a uma planilha".

### 5.7 Interface (`gui/tab_agua.py`) e CLI

`AbaAgua` (pastas → mapa de contas → opções → processar → salvar) e `AbaAguaConcatenar` (planilha base + pastas
novas). Na CLI: `--agua DIR` (repetível), `--mapa-contas ARQ`, `--sem-ocr`, com `--saida`, `--csv`, `--cache`,
`--paralelo`, `--log`.

## 6. Cache, paralelismo e linha de comando

* **Energia**: `cli.processar_lote` usa um pool de processos (`--paralelo`, padrão CPUs − 1) e um cache JSON por PDF em
  `cache_faturas/` (chave: versão do app + caminho + tamanho + mtime); só PDFs novos ou alterados são lidos de novo.
* **Água**: `controller_agua.processar_pastas` usa threads (o Tesseract é um processo externo) e o cache
  `cache_agua/` com a mesma ideia.
* Saídas: `.xlsx` (+ um CSV por aba com `--csv`), `<saida>_erros.txt` com os PDFs que falharam e o log.

## 7. O bot: o mesmo extrator dentro da VM

O bot (`tjgo_faturas_db/bot/geestor_bot`, serviço `geestor-bot` na VM) não reimplementa nada da extração: ele chama a
CLI do app instalado em `/home/geestor/app/src` (a mesma árvore `faturas_app` deste repositório).

1. **Classificação** (`classificar.tipo_pdf`): pelo conteúdo, cada PDF recebido (chat, Drive ou repositório) é
   `agua` (com a concessionária — usa `faturas_app.core.agua.identificar`), `bordero`, `fatura` (EQUATORIAL/CHESP) ou
   `outro`. A checagem de água vem antes da de borderô porque o borderô da Saneago também diz "QUANTIDADE DE CONTAS".
2. **Lote** (`processar.py`): pasta `<lote>/{equatorial,chesp,borderos,agua}`; `rodar_extrator` executa
   `python -m faturas_app --cli --pasta … ` para energia e `--cli --agua …` para água (cache em `saida/cache_faturas`
   e `saida/cache_agua`).
3. **Análise** (`carga.analisar` + `carga_agua.analisar`): lê os JSONs do cache, confere duplicidade (mesmo sha256,
   mesmo id de fatura/borderô no banco ou no lote) e se o PDF é da organização (recusa o que já está em outro banco);
   devolve o status de cada arquivo.
4. **Aprovação e inserção** (`solicitacoes.py` → `carga.inserir` + `carga_agua.inserir`): como o role admin da
   organização, numa transação: `tabelas_fatura.*` / `tabelas_bordero.*` (energia) e `tabelas_agua.*` (água: `pdf`,
   `fatura`, `item`, `historico`, `bordero`, `conta_bordero`), cópia dos PDFs para `/home/geestor/pdfs/<org>/…`
   (água em `agua/<fornecedor>/<AAAA>/`, `agua/saneago_borderos/`, `agua/saneago_analiticas/`) e recompilação das
   views. Os snapshots do banco registram cada linha inserida com autor.
5. **Consulta**: `views_agua.*` (`faturas`, `itens`, `historico`, `borderos`, `contas_bordero`, `bordero_x_analitica`,
   `resumo_mensal`, `contas`, `validacao`, `glossario`, `fornecedores`) alimentam `/agua`, `/exportar planilha_agua`,
   `/query` (prefixo `views_agua.`), `/pdf agua`, `/pdf menu` e o Power BI.
6. **Carga inicial** (`scripts/vm/carga_agua.py`, disparada por `scripts/implantar_agua.py`): inventário do staging,
   resultados extraídos (na origem ou na VM), gravação por `COPY`, mapa de contas e glossário, cópia dos PDFs.

## 8. Aplicativo desktop × bot — comparação de funcionalidades

| Funcionalidade | Aplicativo desktop | Bot @doc_gEEstor_bot |
|---|---|---|
| Extrair faturas Equatorial/CHESP | sim (aba Processar faturas) | sim (`/processar`, `/importar`) — mesma CLI |
| Extrair borderôs de energia | sim (Borderôs de Energia) | sim |
| Extrair faturas de água (12 concessionárias, borderô e analítica Saneago) | sim (aba Água) | sim — reconhecimento automático da concessionária |
| OCR de PDFs digitalizados | sim (Tesseract embutido) | sim (Tesseract da VM) |
| Onde os dados ficam | planilha Excel local (+ CSV) | PostgreSQL da organização (tabelas + views), com snapshots |
| Deduplicação | por id ao adicionar a uma planilha | por sha256 e por id, no lote e contra o banco |
| Validação | aba `validacao` / `validacao_agua` | views `validacao` / `views_agua.validacao`, `/validacao`, `/agua validacao` |
| Mapa de UCs / mapa de contas | local (`%APPDATA%`), importar/gerar | no banco (`tabelas_mapa.uc`, `tabelas_agua.mapa_conta`), `/mapa`, carga por script |
| Cruzamentos | borderô × UCs (energia); borderô × analítica (água) na validação | views `bordero_x_fatura` e `views_agua.bordero_x_analitica` |
| Renomear/ocultar colunas | sim (perfil salvo na planilha) | não (views fixas + views criadas por `/query`) |
| Hardcodes (correções SE→ENTÃO) | locais, aplicados na planilha | por organização, aplicados só nas views, `/hardcodes menu` |
| Consultas ad hoc | no Excel | `/query` (SQL sobre views), `/gem` (Gemini monta a consulta), texto livre interpretado |
| Planilhas | Salvar planilha… | `/exportar <view|planilha|planilha_agua|tudo>`, `/exportar menu` |
| PDFs originais | ficam nas pastas do usuário | repositório na VM: `/pdf`, `/pdf agua`, `/pdf menu` (zip) |
| Power BI | ler a planilha | conexão direta ao banco (`/powerbi`), inclusive `views_agua` |
| Controle de acesso | não se aplica (máquina do usuário) | login por organização, papéis, aprovação do administrador, auditoria |
| Múltiplas organizações | uma planilha por vez | TJGO, UFG, Polícia Penal — um banco cada |
| Atualização | aviso obrigatório ao abrir (Releases do GitHub) | código implantado na VM pelo administrador |
| Funciona sem internet | sim | não (Telegram + VM) |

## 9. Testes, build e publicação

* `PYTHONPATH=src python -m pytest tests -q` — 147 testes; `tests/test_agua.py` usa páginas sintéticas no layout real
  (borderô Saneago 2024, fatura GSAN 2024) para cobrir a leitura por posição, a categoria dos itens, a validação, a
  planilha e a concatenação, além da comparação de versões da atualização obrigatória.
* `build\build_tudo.ps1` gera `dist\FaturasDeEnergia.zip` (portátil) e `dist\FaturasDeEnergia-Setup.exe` (Inno Setup);
  `FATURAS_SELFCHECK=arquivo` faz o exe se autoverificar (módulos, OCR, glossários de energia e água).
* Releases no GitHub: a tag mais recente é o que `core/atualizacao.py` compara com `__version__` para exigir a
  atualização.

## 10. Limitações conhecidas

* **OCR** — em borderôs digitalizados da Saneago (2021–2023) algumas linhas saem com valor trocado; `bate_total = NÃO`
  e a observação apontam a diferença; a analítica da mesma competência serve de conferência. DEMAE Panamá (todo
  digitalizado, imóvel devolvido ao município) e Abadiânia 2021 têm extração parcial (`observacao` indica).
* **SAAE Mineiros 2026** — as guias são imagem; a leitura por OCR cobre conta, referência, vencimento, leituras, itens
  e total, mas sem garantia de todos os itens.
* **SANESC** não imprime número de fatura: o id é `SANESC_<cadastro>_<AAAA-MM>`.
* **SAAE Abadiânia** — a competência é o mês de faturamento impresso (`MÊS FAT.`), um mês depois do consumo.
* **CODEGO** — sem PDF no acervo; extrator experimental.
* Categorias de valor são heurísticas por palavra (`categoria_valor`): tarifas fixas/básicas e IRPJ ficam em `taxas`,
  o que reproduz o critério "taxas = total − água − esgoto" do projeto original.
