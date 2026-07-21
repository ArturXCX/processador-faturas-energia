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

Recursos transversais: **OCR embutido** (faturas CHESP escaneadas), coluna de
**link do PDF**, **mapa de UC** (troca id_uc antigo→novo), **glossário**
automático, **nome do arquivo** configurável, e carimbo de **última atualização**.

---

## 2. Abas e colunas da planilha gerada

Ordem de saída: `fatura_resumida` → `fatura` → `unidade_consumidora` →
`itens_fatura` → `impostos` → `medicao` → `medicao_resumida` → `glossario`
(+ aba oculta `_faturas_meta` com metadados).

| Aba | Conteúdo | Origem |
|---|---|---|
| `fatura` | 1 linha/fatura: id, datas, valor, medidor, dados fiscais, classificação, SCEE, leituras | processador |
| `unidade_consumidora` | dados da UC (razão social, CNPJ, endereço, primeira/última competência e fatura); **1 linha por UC** (drop_duplicates ao final) | processador |
| `itens_fatura` | itens (energia, demanda, tributos, ajustes); tem `id_uc` | processador |
| `impostos` | PIS/PASEP, COFINS, ICMS | processador |
| `medicao` | grandezas medidas por posto horário | processador |
| `fatura_resumida` | **1ª aba**; subconjunto de `fatura` (inclui `valor_total_r$` e `medidor`) | **derivada** de `fatura` |
| `medicao_resumida` | `medicao` só de `ENERGIA GERAÇÃO - KWH`, `Consumo kWh`→`energia_geracao_kwh` | **derivada** de `medicao` |
| `glossario` | significado de colunas/valores/itens (412+ termos) | `core/glossario.py` |

Colunas-chave especiais:
- **`id_fatura`** leva prefixo da fornecedora (`EQUATORIAL_…`/`CHESP_…`) e liga
  todas as abas. **`numero_fatura`** guarda o valor original (= nome do PDF no
  Drive — preserva a busca do `link_pdf`).
- **`id_uc`** aparece em TODAS as abas; quando a fatura não traz UC, recebe
  `NULO_<id_fatura>` (nunca vazio — feito em `equatorial.carimbar_id_uc_competencia`,
  usado também pela CHESP). Logo ao lado, sempre nesta ordem: **`id_uc_sem_format`**
  (sem ponto/hífen), **`id_uc_atual_medidor`** (por medidor, o id_uc mais recente
  e não-`NULO_`) e **`id_uc_atual_medidor_sem_format`**. **`competencia`** aparece
  em todas as abas exceto `unidade_consumidora`.
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
├── __main__.py          entrada; modo selfcheck (env FATURAS_SELFCHECK=<arquivo>)
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
│   ├── derivados.py     colunas recalculadas do zero: unidade_consumidora.(primeira|ultima)_*, id_uc_atual_medidor(+sem_format), medidor, item_normalizado
│   ├── equivalencias.py tabela item→item_normalizado persistida em %APPDATA%/FaturasEnergia
│   ├── glossario.py     monta a aba glossario (docs + conceitos + itens do PDF)
│   ├── build_info.py    lê o carimbo de data/hora da última atualização
│   └── controller.py    orquestra o processamento das pastas (progresso/cancelar)
├── gui/                 INTERFACE (CustomTkinter)
│   ├── app.py           janela principal (cabeçalho + 2 abas); handler global de erros
│   ├── tab_processar.py aba 1 (PDF → planilha)
│   ├── tab_concatenar.py aba 2 (upload + novas faturas → concatena)
│   ├── columns_editor.py editor de colunas/abas
│   ├── tab_parametros.py aba 3: tabela de equivalências de itens (editável, persistida)
│   ├── mapping_dialog.py tela de mapeamento (quando não há metadados)
│   ├── widgets.py       SeletorPastas, SeletorLink, PainelProgresso
│   └── worker.py        processamento em thread + fila de eventos
└── resources/           glossario_itens.json (301 itens), build_info.txt (carimbo)
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
4. `profile.Perfil.padrao_de_dataframes` cria o perfil (nomes = canônicos;
   colunas 100% vazias já desmarcadas). O usuário edita no `columns_editor`.
5. `glossario.garantir_glossario` acrescenta a aba glossario.
6. `excel_io.escrever_workbook` aplica o perfil, estiliza e grava, incluindo a
   aba oculta `_faturas_meta` (mapa nome_exibido → canônico).

### Concatenar (aba 2)
1. `excel_io.ler_workbook` lê a planilha base (+ metadados, se houver).
2. Processa as novas faturas (igual acima) → DataFrames canônicos.
3. Define o mapa nome_exibido→canônico de cada aba: dos **metadados** embutidos
   ou, se ausentes, por **auto-sugestão** + tela de mapeamento (`mapping_dialog`).
4. `concat.concatenar` traduz as novas faturas para o **layout da planilha
   enviada** (respeitando renomeações/exclusões) e empilha, com dedup.
5. `uc_map.aplicar` (opcional) + `glossario.garantir_glossario` + salvar.

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

### Casos de parsing conhecidos (Equatorial, `equatorial.py`)
- **Leitura Anterior opcional** na medição: linha com 1 só inteiro (célula vazia
  no PDF) não é perdida (`pat_a` com grupo opcional).
- **RELIGAÇÃO/DESLIGAMENTO PROGRAMADO**: itens financeiros COM quantidade
  (nome+qtd+preço+valor) — tratados no padrão `mem` junto de EMIS. SEGUNDA VIA.
- **DEMANDA ISENTO DE ICMS**: às vezes alíquota `0` sem `%` e sem coluna ICMS (7
  tokens) — padrão dedicado `m_isento` (senão a tarifa recebia a base).
- **SCEE `SALDO KWH`**: 3 formatos — número único; `ATV:`/`ATV=` (equivale ao
  total); por posto `P=.., FP=.., HR=..`. A captura usa **DOTALL** porque o bloco
  pode quebrar em duas linhas (HR embaixo).

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
implementar a derivação em `dataset.Dataset.to_dataframes`.

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

**Validar o `.exe`:** rodar com `FATURAS_SELFCHECK=<arquivo>` no ambiente — o app
grava um relatório (imports, OCR, glossário) e sai sem abrir a janela. Truque:
a contagem de termos do glossário no relatório muda quando o código muda, então
serve para confirmar que o pacote tem a versão nova.

---

## 9. Testes

- `tests/test_concat.py` — lógica de concatenação/remapeamento (sem PDFs).
  Rodar: `PYTHONPATH=src .venv\Scripts\python.exe tests\test_concat.py`.
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
