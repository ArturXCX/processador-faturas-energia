# Como o extrator funciona — documentação técnica completa (v4.3)

Esta documentação explica, arquivo por arquivo, como o **Processador de Faturas de Energia e Água** transforma PDFs em
dados estruturados, e compara o que o **aplicativo desktop** e o **site gEEstor** fazem com esse
mesmo núcleo. Complementa o [README](../README.md) (visão geral e build), o [manual de uso](MANUAL_DE_USO.md)
(passo a passo com capturas de tela) e, no projeto da VM, `DOCUMENTACAO_COMPLETA_GEESTOR.md` (bancos, site, servidor).

Sumário

1. [Ideia central: um núcleo, duas superfícies](#1-ideia-central-um-núcleo-duas-superfícies)
2. [Mapa dos arquivos](#2-mapa-dos-arquivos)
3. [Energia — faturas individuais (Equatorial / CHESP)](#3-energia--faturas-individuais-equatorial--chesp)
4. [Energia — borderôs (faturas agrupadas)](#4-energia--borderôs-faturas-agrupadas)
5. [Água — todas as concessionárias no mesmo modelo](#5-água--todas-as-concessionárias-no-mesmo-modelo)
6. [Cache, paralelismo e linha de comando](#6-cache-paralelismo-e-linha-de-comando)
7. [O site gEEstor: o mesmo extrator dentro da VM](#7-o-site-geestor-o-mesmo-extrator-dentro-da-vm)
8. [Aplicativo desktop × site — comparação de funcionalidades](#8-aplicativo-desktop--site--comparação-de-funcionalidades)
9. [Testes, build e publicação](#9-testes-build-e-publicação)
10. [Limitações conhecidas](#10-limitações-conhecidas)

---

## 1. Ideia central: um núcleo, duas superfícies

Todo o conhecimento sobre os PDFs está no pacote Python `faturas_app` (pasta `src/`). Ele **não depende de interface**:
recebe caminhos de PDF e devolve linhas em **colunas canônicas** (nomes fixos, definidos em `core/schema.py` para energia
e `core/agua/schema_agua.py` para água). Sobre esse núcleo há duas superfícies:

* o **aplicativo desktop** (`gui/`, CustomTkinter), empacotado com PyInstaller — roda na máquina do usuário e grava
  planilhas Excel;
* a **linha de comando** (`cli.py`, `python -m faturas_app --cli …`), que é exatamente o que o **site gEEstor** chama na VM para
  processar cada lote; o site então grava as mesmas linhas nas tabelas do PostgreSQL.

Consequência prática: um PDF lido no desktop e o mesmo PDF lido pelo site produzem **as mesmas colunas e os mesmos
valores**; o que muda é o destino (planilha × banco) e o que se faz depois (editar colunas × consultar/aprovar/auditar).

```
PDF ──► extrator (faturas_app.core) ──► linhas canônicas ──┬──► planilha Excel (desktop / CLI)
                                                            └──► tabelas_* no PostgreSQL (site, carga inicial)
```

## 2. Mapa dos arquivos

```
src/faturas_app/
├── __init__.py              __version__ (4.3.0) e APP_NAME
├── __main__.py              entrada: GUI, --cli, e autoverificação do exe (FATURAS_SELFCHECK)
├── cli.py                   modo linha de comando: energia (--pasta) e água (--agua), cache, paralelo, CSV, log
├── core/
│   ├── schema.py            colunas CANÔNICAS de energia por aba, apelidos, chaves de dedup, cores das abas
│   ├── equatorial.py        extrator de faturas Equatorial/ENEL (texto do PDF + regex por bloco)
│   ├── chesp.py             extrator de faturas CHESP (texto ou OCR)
│   ├── enel.py              faturas antigas da ENEL/CELG D (2018–2022, digitalizadas): OCR + reconciliação com o total
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

**Itens que a leitura por seção não alcança (v4.2).** Se a soma dos itens não fecha com o total impresso, `equatorial._completar_itens`
procura no texto as linhas fora do lugar e as acrescenta, desde que a diferença diminua: as retenções federais do layout antigo
("IR (1,2%)LEI 9430(-)", na mesma linha da medição) e os itens que continuam na 2ª página ao lado dos impostos (MULTA, JUROS, VALOR
CORREÇÃO IPCA, ICMS ENERGIA INJET RET, COMPENSAÇÃO DE DIC, PAGAMENTO A MAIOR). Fatura que já fecha nunca muda. Nas 2.242 faturas da UFG de
2023–2026, as que não fechavam caíram de 322 para 0.

### 3.1 ENEL — faturas antigas digitalizadas (v4.1, `core/enel.py`)

Faturas da ENEL/CELG D de 2018 a início de 2022, anteriores ao DANF3E, quase sempre **digitalizadas** (o texto embutido,
quando existe, é o OCR ruim do scanner). Três layouts: **GRUPO_A** (dois itens por linha, PRODUTO QUANTIDADE TARIFA
VALOR ×2, memória de cálculo da medição numa página à parte), **B_2018** (coluna LANÇAMENTOS à direita) e **B_2020**
("ITENS QTD VALOR UNIT. VALOR" ×2 e canhoto). Como funciona:

1. OCR próprio (Tesseract, 300 dpi) da página do corpo — que pode não ser a 1ª (verso escaneado antes) nem estar de pé
   (OSD/180°) — com as **caixas das palavras**; pelo cabeçalho do quadro de itens recortam-se as **colunas de itens**, que
   são lidas de novo sozinhas e ampliadas; o total e o canhoto também são relidos em recorte.
2. Cada item fica com **várias leituras candidatas** (o OCR troca asterisco por dígito, perde vírgula, perde o sinal),
   mais quantidade × tarifa (a ENEL **trunca** os centavos).
3. **Programação dinâmica**: escolhe uma leitura por item para que a soma dê **exatamente o total** impresso (e o
   fornecimento dê a base do ICMS, quando legível); um total "lixo" que só fecharia trocando muitos itens é recusado.
   Um único item ilegível pode fechar pela diferença, e uma linha de retenção perdida é reposta — sempre com aviso em
   `mensagens_importantes`.
4. Nomes dos itens iguais aos da Equatorial (`CONSUMO FP`, `PARCELA TE P`, `ADC BAND. AMARELA TE HR`,
   `COFINS LEI 9430(-)`…), para a série histórica ficar contínua. `id_fatura = ENEL_<UC>_<AAAAMM>`.

`processar_pdf(pdf, dicas={'valor_total': …})` aceita o líquido da UC no borderô como reforço do total. DANF3E com texto
nativo vai para `equatorial.py`; DANF3E **escaneado** em baixa resolução sai só com cabeçalho, total e tributos
(`_somente_cabecalho`; o controller não o descarta). Medido no acervo do INMETRO (86 faturas 2018–2022): 74 fecham sozinhas
e as 12 restantes com o total do borderô; todas as que fecham sozinhas batem com o borderô.

## 4. Energia — borderôs (faturas agrupadas)

`core/borderos.py` lê o borderô da Equatorial/ENEL (várias UCs num único documento):

* **identidade** vem do conteúdo (número da fatura agrupada, código de agrupamento, competência, vencimento); o nome do
  arquivo é só o último recurso;
* **scans com texto embutido ruim** (v4.1): se a leitura pelo texto do PDF não reconcilia, o borderô é relido inteiro por
  OCR e fica a leitura que fecha (ou que acha mais UCs); se a soma das UCs aparece impressa como valor, ela é o total;
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

* **Borderô da Saneago com pouca tabela** — títulos grandes puxam a mediana para cima (≈ 4,0 pt contra ≈ 3,05 pt da
  fonte da tabela); o logradouro longo estoura as colunas e empurra os números uma coluna para a direita, sem que o total
  deixe de fechar. Só para esse documento, `Documento.repaginar()` refaz o layout com o **1º quartil** da largura.
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
* **Modelo de OCR das tabelas da Saneago (v4.2)** — em borderôs e analíticas digitalizados da Saneago, `extrator.processar_pdf` lê também
  com o modelo rápido `por_fast.traineddata` (de tessdata_fast, 2 MB) e fica com ele se não piorar (`_nota_leitura`). No borderô de out/2023, o
  modelo padrão de 15 MB não fechava nenhuma coluna; o rápido fecha todas. Nas faturas individuais o resultado é misto, por isso o padrão continua o
  de 15 MB. Sem o arquivo instalado, tudo segue como antes.
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
`valor_multa_juros`), `soma_itens`, `valor_irpj` (soma dos itens com a palavra IRPJ, com o sinal impresso; vazio se a
fatura não discrimina) e `valor_bruto` (`valor_total − valor_irpj`); o IRPJ continua somado em `valor_taxas`. Quando o PDF foi lido por OCR e o nome do arquivo traz `FATURA Nº n`, o número do
arquivo prevalece sobre o do OCR.

**Borderô da Saneago: conferência por coluna e releitura.** Além do `bate_total`, `saneago_bordero.colunas_divergentes`
compara a soma das contas com o rodapé em água, esgoto, SMRSU (tolerância de R$ 0,05) e consumo (igualdade exata); o que
não fecha vai para `observacao` (`soma por coluna difere do rodapé: …`). Se o PDF é digitalizado e alguma coluna diverge,
`extrator.processar_pdf` relê a 400 e, se preciso, 500 dpi e fica, por borderô, com a leitura de menor divergência
(`relido por OCR a N dpi para fechar com o rodapé`). **A releitura só traz números**: conta, nome, logradouro, ordem, ids,
competência e datas são sempre os da leitura de 300 dpi, e só entra borderô alinhado (mesmo id, mesmo número de contas,
contas compatíveis) que não perca rodapé lido. Com OCR, `_numeros_da_cauda` ignora ruído entre dois números (`ak`, `TÁ!`,
`AE)`), mas não partes de endereço (`S/N`, `QD.`, `Nº`, `1º`, `(2)`). Competência que o OCR não leu vem do nome do arquivo.

### 5.5 Mapa de contas, derivados e validação

* `mapa_conta.py` — JSON em `%APPDATA%\FaturasEnergia\mapa_contas_agua.json`; chave = dígitos da conta sem zeros à
  esquerda dentro do fornecedor; `importar()` lê o `DICIONARIO_AGUA.json` do TJGO (CONTA_DV, CONTA,
  UNIDADE JUDICIÁRIA, ENDEREÇO, DISTRIBUIDORA, HIDRÔMETRO_ATUAL, OPERANTES, IRPJ_APLICAÇÃO, AGUA, ESGOTO, SMRSU), o `contas.json` do
  projeto original ou uma planilha; `construir_de_extracao()` monta o mapa a
  partir das faturas (um registro por fornecedor + conta, consolidando nome, endereço, hidrômetro, serviços e
  competências) — foi assim que o primeiro mapa do acervo do TJGO foi gerado; desde nov/2026 o banco usa o dicionário
  (`scripts/importar_mapa_agua.py`, com as leituras erradas de OCR já conferidas como identificadores da conta certa).
* `derivados_agua.py` — `conta_canonica` / `unidade_institucional` em todas as linhas (uma fatura digitalizada sem
  conta legível herda a conta do mapa quando a concessionária tem **uma única conta** possível (a única do mapa ou,
  havendo contas extintas no mapa, a única lida nas faturas) — Buriti Alegre, Leopoldo de Bulhões, SANESC, Corumbá, Abadiânia, DEMAE Panamá —, com a ocorrência `CONTA_INFERIDA_PELO_MAPA`);
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

## 7. O site gEEstor: o mesmo extrator dentro da VM

O site (`tjgo_faturas_db/web/geestor_web`, serviço `geestor-web` na VM, https://unigeestor.emc.ufg.br) não reimplementa nada da
extração: ele chama a CLI do app instalado em `/home/geestor/app/src` (a mesma árvore `faturas_app` deste repositório). O bot do
Telegram, que fazia o mesmo papel, foi desativado em 12/11/2026; a biblioteca dele (`geestor_bot`: classificação, carga, aprovação)
continua em uso pelo site.

**Sincronia com o GitHub.** O que está em `/home/geestor/app/src` é sempre a branch principal (`master`) deste repositório: o timer
`geestor-extrator-sync` da VM consulta o GitHub a cada 5 minutos e, quando a branch muda, baixa o commit, confere a versão nova
rodando o próprio worker do site numa amostra fixa de PDFs (cada arquivo tem de sair com o mesmo tipo e o mesmo identificador, sem
erro), troca a versão em uso, reinicia o site e avisa os administradores. Se a conferência falhar, ou se a versão do commit for
menor que a de produção, nada é trocado e o aviso diz o motivo. Portanto: **mesclar na `master` é publicar no site**. O aplicativo
de mesa continua sendo atualizado pelas Releases (seção 9). Detalhes em `tjgo_faturas_db/scripts/vm/sincronizar_extrator.py`.

1. **Classificação** (`geestor_bot.classificar.tipo_pdf`): pelo conteúdo, cada PDF enviado é `agua` (com a concessionária — usa
   `faturas_app.core.agua.identificar`), `bordero`, `fatura` (EQUATORIAL/CHESP/ENEL) ou `outro`. A checagem de água vem antes da de
   borderô porque o borderô da Saneago também diz "QUANTIDADE DE CONTAS".
2. **Lote** (`geestor_web/worker.py processar`): pasta `<lote>/{equatorial,chesp,enel,borderos,agua}`; o worker chama
   `faturas_app.cli.main` para energia e para água (cache em `saida/cache_faturas` e `saida/cache_agua`) e
   `core.borderos.processar_pdf` para os borderôs; grava as planilhas e `resultado.json`.
3. **Análise** (`carga.analisar` + `carga_agua.analisar`): lê os JSONs do cache, confere duplicidade (mesmo sha256, mesmo id de
   fatura/borderô no banco ou no lote) e se o PDF é da organização (recusa o que já está em outro banco).
4. **Aprovação e inserção** (página Solicitações → `carga.inserir` + `carga_agua.inserir`): como o papel de administração da
   organização, numa transação: `tabelas_fatura.*` / `tabelas_bordero.*` (energia) e `tabelas_agua.*` (água), cópia dos PDFs para
   `/home/geestor/pdfs/<org>/…` e recompilação das views. Os snapshots do banco registram cada linha inserida com autor.
5. **Consulta**: as views `views_faturas.*`, `views_borderos.*` e `views_agua.*` alimentam as páginas do site, as planilhas
   exportadas e o Power BI.
6. **Conferência e justificativas**: as regras de `validacao` aparecem em Conferência; quem confere um alerta no PDF e vê que está
   certo registra a justificativa, que tira o alerta do quadro e fica na página do documento.

## 8. Aplicativo desktop × site — comparação de funcionalidades

| Funcionalidade | Aplicativo desktop | Site gEEstor |
|---|---|---|
| Extrair faturas Equatorial/CHESP/ENEL | sim (aba Processar faturas) | sim (Extrator / Inserir) — mesma CLI |
| Extrair borderôs de energia | sim (Borderôs de Energia) | sim |
| Extrair faturas de água (12 concessionárias, borderô e analítica Saneago) | sim (aba Água) | sim — reconhecimento automático da concessionária |
| OCR de PDFs digitalizados | sim (Tesseract embutido) | sim (Tesseract da VM) |
| Onde os dados ficam | planilha Excel local (+ CSV) | PostgreSQL da organização (tabelas + views), com snapshots |
| Deduplicação | por id ao adicionar a uma planilha | por sha256 e por id, no lote e contra o banco |
| Validação | aba `validacao` / `validacao_agua` | páginas Conferência (energia, água, borderôs), com justificativas |
| Mapa de UCs / mapa de contas | local (`%APPDATA%`), importar/gerar | no banco (`tabelas_mapa.uc`, `tabelas_agua.mapa_conta`) |
| Cruzamentos | borderô × UCs (energia); borderô × analítica (água) na validação | views `bordero_x_fatura` e `views_agua.bordero_x_analitica` |
| Renomear/ocultar colunas | sim (perfil salvo na planilha) | não (views fixas) |
| Hardcodes (correções SE→ENTÃO) | locais, aplicados na planilha | por organização, aplicados só nas views |
| Planilhas | Salvar planilha… | exportação por página e planilha completa |
| PDFs originais | ficam nas pastas do usuário | repositório na VM, com link público por documento |
| Power BI | ler a planilha | conexão direta ao banco (página Power BI), inclusive `views_agua` |
| Controle de acesso | não se aplica (máquina do usuário) | login por organização, papéis, aprovação do administrador, auditoria |
| Múltiplas organizações | uma planilha por vez | TJGO, UFG, Polícia Penal, INMETRO — um banco cada |
| Atualização | aviso obrigatório ao abrir (Releases do GitHub) | automática: segue a branch `master` (seção 7) |
| Funciona sem internet | sim | não |

## 9. Testes, build e publicação

* `PYTHONPATH=src python -m pytest tests -q` — 156 testes (`tests/test_enel.py`: números do OCR, itens, reconciliação); `tests/test_agua.py` usa páginas sintéticas no layout real
  (borderô Saneago 2024, fatura GSAN 2024) para cobrir a leitura por posição, a categoria dos itens, a validação, a
  planilha e a concatenação, além da comparação de versões da atualização obrigatória.
* `build\build_tudo.ps1` gera `dist\FaturasDeEnergia.zip` (portátil) e `dist\FaturasDeEnergia-Setup.exe` (Inno Setup);
  `FATURAS_SELFCHECK=arquivo` faz o exe se autoverificar (módulos, OCR, glossários de energia e água).
* Releases no GitHub: a tag mais recente é o que `core/atualizacao.py` compara com `__version__` para exigir a
  atualização.

## 10. Limitações conhecidas

* **OCR** — em borderôs digitalizados da Saneago (2021–2023) o OCR pode não ler um dígito nem a 500 dpi; `bate_total = NÃO`
  e `soma por coluna difere do rodapé` na observação apontam a diferença; a analítica da mesma competência serve de conferência.
  O dígito verificador 0 lido como a letra O (`1650402 O FÓRUM…`) continua saindo assim no PDF lido; no banco, o mapa liga essa leitura à conta certa. DEMAE Panamá (todo
  digitalizado, imóvel devolvido ao município) e Abadiânia 2021 têm extração parcial (`observacao` indica).
* **SAAE Mineiros 2026** — as guias são imagem; a leitura por OCR cobre conta, referência, vencimento, leituras, itens
  e total, mas sem garantia de todos os itens.
* **SANESC** não imprime número de fatura: o id é `SANESC_<cadastro>_<AAAA-MM>`; `data_leitura_anterior` fica vazia em todos os modelos.
* **SAAE Abadiânia** — a competência é o mês de faturamento impresso (`MÊS FAT.`), um mês depois do consumo.
* **CODEGO** — sem PDF no acervo; extrator experimental.
* Categorias de valor são heurísticas por palavra (`categoria_valor`): tarifas fixas/básicas e IRPJ ficam em `taxas`,
  o que reproduz o critério "taxas = total − água − esgoto" do projeto original.
