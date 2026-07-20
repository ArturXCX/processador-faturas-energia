# Processador de Faturas de Energia (Equatorial / CHESP)

Aplicativo desktop (Windows) que converte PDFs de faturas de energia em uma
planilha Excel com 5 abas (`fatura`, `cliente`, `itens_fatura`, `impostos`,
`medicao`), permite editar/renomear colunas e abas, e concatenar novas faturas a
uma planilha já existente. Distribuído como executável — o usuário final **não
precisa de Python instalado**.

## 📥 Download

Baixe a versão mais recente na página de **[Releases](../../releases/latest)**:
- **`FaturasDeEnergia-Setup.exe`** — instalador (recomendado; sem terminal).
- **`FaturasDeEnergia.zip`** — versão portátil (extrair e abrir o `.exe`).

Todas as versões publicadas, da mais recente à mais antiga, ficam em
**[Releases](../../releases)**.

A lógica de extração foi portada fielmente dos notebooks originais de
prototipagem (processadores Equatorial e CHESP + concatenador). Esses notebooks
não são versionados neste repositório por conterem dados reais de faturas
(ver `.gitignore`).

> **Retomando o projeto numa nova sessão? Comece por [CONTEXTO.md](CONTEXTO.md)** —
> handoff completo (ambiente, estado atual, esquema, pegadinhas, pendências).
> Para arquitetura detalhada, [DOCUMENTACAO.md](DOCUMENTACAO.md).

---

## Para o usuário final

Veja **[LEIA-ME.txt](LEIA-ME.txt)** (incluído no `.zip`). Resumo: extrair o zip,
abrir `FaturasDeEnergia.exe`, processar pastas de PDFs e salvar a planilha.

---

## Arquitetura

```
src/faturas_app/
├── core/                 # núcleo, sem dependência de GUI
│   ├── schema.py         # esquema CANÔNICO (colunas internas fixas) + apelidos + chaves de dedup
│   ├── equatorial.py     # processador Equatorial (porte do notebook)
│   ├── chesp.py          # processador CHESP + OCR (PyMuPDF + pytesseract)
│   ├── ocr.py            # localização do Tesseract (embutido ou do sistema)
│   ├── dataset.py        # acumula linhas canônicas -> DataFrames
│   ├── profile.py        # camada de EXIBIÇÃO (renomear/incluir/excluir) + metadados
│   ├── excel_io.py       # escrita estilizada + aba oculta de metadados / leitura
│   ├── concat.py         # concatenação com remapeamento canônico + dedup
│   └── controller.py     # orquestra o processamento das pastas (progresso/cancelar)
└── gui/                  # interface CustomTkinter
    ├── app.py            # janela principal (2 abas)
    ├── tab_processar.py  # PDF -> planilha
    ├── tab_concatenar.py # upload + novas faturas -> concatena
    ├── columns_editor.py # editor de colunas/abas
    ├── mapping_dialog.py # tela de mapeamento (quando não há metadados)
    ├── widgets.py        # seletor de pastas, painel de progresso
    └── worker.py         # processamento em thread + fila de eventos
```

### Como o conflito de colunas é resolvido (requisito-chave)

O ponto sensível é re-concatenar faturas novas a uma planilha que o usuário já
**renomeou ou teve colunas removidas**. A solução:

1. Os processadores sempre produzem **nomes canônicos** (`schema.py`).
2. O que o usuário renomeia/remove é uma **camada de exibição** (`profile.py`).
3. Ao salvar, gravamos uma **aba oculta `_faturas_meta`** com o mapa
   `nome_exibido → canônico`. No reupload, esse mapa remapeia tudo com exatidão.
4. Se a planilha **não** tiver esses metadados (veio de outro lugar), o app
   **sugere** o mapeamento por similaridade e abre uma **tela de confirmação**
   (`mapping_dialog.py`) — incluindo apelidos como `link_pdf → caminho_pdf`.
5. A concatenação (`concat.py`) traduz as faturas novas para o **layout exato**
   da planilha enviada (respeitando renomeações/remoções) e remove duplicatas
   pela chave canônica de cada aba.

---

## Build (gerar o executável)

Pré-requisitos: **Windows + Python 3.12** e conexão à internet (a 1ª vez baixa o
Tesseract). Tudo é feito num `.venv` isolado para o pacote ficar enxuto.

```powershell
# 1) ambiente e dependências
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-build.txt

# 2) montar o Tesseract portátil (OCR) — uma vez
powershell -ExecutionPolicy Bypass -File build\fetch_tesseract.ps1

# 3) (opcional) gerar o ícone — já versionado em build\app.ico
.\.venv\Scripts\python.exe build\make_icon.py

# 4) empacotar (gera dist\FaturasDeEnergia\ e dist\FaturasDeEnergia.zip)
powershell -ExecutionPolicy Bypass -File build\build.ps1

# 5) (opcional) gerar o instalador setup.exe (precisa do Inno Setup:
#    winget install JRSoftware.InnoSetup)
powershell -ExecutionPolicy Bypass -File build\build_installer.ps1
```

Dois formatos de distribuição são gerados em `dist\`:

- **`FaturasDeEnergia.zip`** (~100 MB) — a pessoa extrai e roda `FaturasDeEnergia.exe`.
- **`FaturasDeEnergia-Setup.exe`** (~72 MB) — instalador por usuário (sem admin),
  cria atalhos no Menu Iniciar / Área de Trabalho. Config em `build/installer.iss`.

> Dica: rode o `setup.exe` a partir do **disco local** (não direto do Google
> Drive) — ler o instalador da nuvem pode deixar a instalação muito lenta.

### Esquema das abas (resumo das colunas-chave)

- `id_fatura` leva **prefixo da fornecedora** (`EQUATORIAL_…` / `CHESP_…`) e liga
  todas as abas; `numero_fatura` guarda o valor **original** (= nome do PDF no
  Drive, preservando a busca do `link_pdf`).
- `itens_fatura` inclui `id_uc` (da fatura correspondente).
- `fatura` inclui `scee_geracao_ciclo` (AAAA_MM) e quatro colunas de saldo do SCEE
  extraídas do bloco "INFORMAÇÕES DO SCEE" (só em UCs do SCEE; vazias nas demais):
  `scee_saldo_kwh_total` (número único após "SALDO KWH:" ou o valor de "ATV:") e
  `scee_saldo_kwh_P` / `_FP` / `_HR` (formato por posto "P=…, FP=…, HR=…").
- Abas **derivadas** (em `dataset.py`, via `BASE_SHEETS`/`DERIVED_SHEETS`):
  - `fatura_resumida` — **primeira aba**; subconjunto de `fatura`.
  - `medicao_resumida` — `medicao` filtrada na grandeza `ENERGIA GERAÇÃO - KWH`,
    com `Consumo kWh` renomeado para `energia_geracao_kwh`.
- Medição (Equatorial): a "Leitura Anterior" é **opcional** no parse — linhas em
  que essa célula vem vazia no PDF (ex.: `DEMANDA GERAÇÃO - KW`/`FORA PONTA`) não
  são mais perdidas.

### Nome do arquivo

Ambas as abas têm um campo "Nome do arquivo" (placeholder `faturas_energia`) que
define o nome sugerido ao salvar.

### Aba de glossário (`core/glossario.py`)

A planilha gerada inclui uma aba `glossario` (404 termos) combinando:
1. **Documentação das abas/colunas/valores** que o app produz (gerada a partir do
   `schema.py`).
2. **Conceitos gerais** de conta de energia (glossário oficial da Equatorial).
3. **301 descrições de itens de faturamento**, extraídas do glossário oficial em
   PDF e embutidas em `resources/glossario_itens.json`.

- **Processar:** a aba é sempre adicionada (`garantir_glossario`).
- **Concatenar:** se a planilha base já tiver a aba (qualquer grafia
  `glossario`/`glossário`), ela é preservada; senão, é acrescentada.

### Coluna de link do PDF (`link_pdf`)

Em ambas as abas há o seletor **"Link do PDF"** (`core/links.py`), que preenche a
coluna canônica `link_pdf`:

- **Caminho local** — não gera link (mantém só `caminho_pdf`).
- **Busca no Drive** — `https://drive.google.com/drive/search?q=<nome>` (zero config;
  abre o Drive buscando a fatura — útil em planilha compartilhada / Power BI).
- **Modelo de URL** — padrão definido pelo usuário com `{arquivo}` / `{arquivo_sem_ext}`.

> Link **exato** por arquivo (`file/d/<id>/view`, como o concatenador do Colab)
> exige a **API do Google Drive** (credenciais + login). Não está embutido para
> manter o app sem configuração; é uma evolução possível (adicionar um 4º modo
> que usa `google-api-python-client` + OAuth e mapeia `arquivo_pdf → id`).

### Sobre o OCR embutido

Cerca de 1/5 das faturas CHESP são escaneadas e exigem OCR. A pasta `tesseract/`
(montada por `fetch_tesseract.ps1` a partir do conda-forge, ~45 MB) é embutida em
`_internal/tesseract/` e encontrada automaticamente por `core/ocr.py`. Não há
dependência de Tesseract instalado no sistema.

---

## Rodar a partir do código (desenvolvimento)

```powershell
.\.venv\Scripts\python.exe -m faturas_app          # abre a interface
# (com src no PYTHONPATH, ou instale: pip install -e .)
```

> O `core/ocr.py` também encontra a pasta `tesseract/` em modo de
> desenvolvimento (ao lado de `src/`), então o OCR funciona sem empacotar.

---

## Limpeza

A pasta `build/_stage/` (download do Tesseract + env do micromamba) pode ser
apagada após montar `tesseract/`. As pastas `build/_work/` e `dist/` são geradas
pelo build e podem ser regeneradas.
