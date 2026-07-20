"""
Esquema canônico das planilhas de faturas.

Este módulo é o "contrato" interno do app. Os PROCESSADORES sempre produzem
colunas com os nomes canônicos definidos aqui. O que o usuário renomeia/exclui
na interface é apenas uma *camada de exibição* por cima destes nomes — e é isso
que torna a re-concatenação robusta: mesmo que a planilha enviada tenha colunas
renomeadas ou removidas, conseguimos remapear cada coluna de volta ao seu nome
canônico (via metadados embutidos ou pela tela de mapeamento).

Os nomes canônicos são idênticos aos nomes de coluna dos notebooks originais,
de modo que, sem nenhuma renomeação, a planilha gerada bate com as de referência.
"""
from __future__ import annotations

# Abas produzidas diretamente pelos processadores (acumuladas por PDF).
BASE_SHEETS = ["fatura", "cliente", "itens_fatura", "impostos", "medicao"]

# Abas DERIVADAS (calculadas a partir das base em Dataset.to_dataframes).
DERIVED_SHEETS = ["fatura_resumida", "medicao_resumida"]

# Ordem das abas na planilha de saída (resumidas posicionadas como pedido).
SHEET_ORDER = ["fatura_resumida", "fatura", "cliente", "itens_fatura",
               "impostos", "medicao", "medicao_resumida"]

# Cores (cabeçalho, linha alternada) — mesmas dos notebooks.
SHEET_COLORS = {
    "fatura":       ("1F4E79", "BDD7EE"),
    "cliente":      ("1F4E79", "BDD7EE"),
    "itens_fatura": ("375623", "E2EFDA"),
    "impostos":     ("7B2C2C", "FCE4D6"),
    "medicao":      ("4A235A", "E8D5F5"),
    "fatura_resumida":   ("1F4E79", "BDD7EE"),
    "medicao_resumida":  ("4A235A", "E8D5F5"),
    "glossario":    ("0E6E63", "D6EFEC"),
}

# Colunas canônicas de cada aba, em ordem. A união Equatorial+CHESP segue a
# ordem da Equatorial; colunas exclusivas entram ao final.
#
# 'id_uc' e 'competencia' aparecem em TODAS as abas (competencia exceto em
# 'cliente'); 'link_pdf' guarda o link do PDF (busca no Drive pelo nome do arquivo).
CANONICAL_COLUMNS = {
    "fatura": [
        "id_fatura",
        "numero_fatura",
        "arquivo_pdf",
        "link_pdf",
        "fornecedor",
        "id_uc",
        "data_emissao",
        "competencia",
        "data_vencimento",
        "valor_total_r$",
        "numero_nf",
        "serie_nf",
        "cfop",
        "chave_acesso_nfe",
        "protocolo_autorizacao",
        "data_hora_protocolo",
        "classificacao_tarifaria",
        "tipo_fornecimento",
        "tensao_nominal_v",
        "tensao_min_v",
        "tensao_max_v",
        "demanda_contratada_kw",
        "demanda_geracao_contratada_kw",
        "perdas_transformacao_pct",
        "scee_geracao_ciclo",
        "scee_saldo_kwh_total",
        "scee_saldo_kwh_P",
        "scee_saldo_kwh_FP",
        "scee_saldo_kwh_HR",
        "data_leitura_anterior",
        "data_leitura_atual",
        "numero_dias_leitura",
        "data_proxima_leitura",
    ],
    "cliente": [
        "id_uc",
        "razao_social",
        "cnpj",
        "cep",
        "municipio",
        "uf",
        "ultima_competencia",
        "ultima_fatura",
    ],
    "itens_fatura": [
        "id_fatura",
        "id_uc",
        "competencia",
        "item",
        "tipo",
        "unidade",
        "quantidade",
        "preco_unitario_com_tributos_r$",
        "valor_r$",
        "pis_cofins",
        "base_calc_icms_r$",
        "aliquota_icms_r$",
        "icms",
        "tarifa_unitaria_r$",
    ],
    "impostos": [
        "id_fatura",
        "id_uc",
        "competencia",
        "Tributo",
        "Base (R$)",
        "Aliquota (%)",
        "Valor (R$)",
    ],
    "medicao": [
        "id_fatura",
        "id_uc",
        "competencia",
        "Grandezas",
        "Postos horarios",
        "Leitura Anterior",
        "Leitura Atual",
        "Const Medidor",
        "Consumo kWh",
        "Medidor",
    ],
    # ── Abas DERIVADAS ──────────────────────────────────────────────────────
    "fatura_resumida": [
        "id_fatura",
        "numero_fatura",
        "id_uc",
        "competencia",
        "classificacao_tarifaria",
        "tipo_fornecimento",
        "demanda_contratada_kw",
        "demanda_geracao_contratada_kw",
        "scee_geracao_ciclo",
        "scee_saldo_kwh_total",
        "scee_saldo_kwh_P",
        "scee_saldo_kwh_FP",
        "scee_saldo_kwh_HR",
        "numero_dias_leitura",
    ],
    "medicao_resumida": [
        "id_fatura",
        "id_uc",
        "competencia",
        "Grandezas",
        "Postos horarios",
        "Leitura Anterior",
        "Leitura Atual",
        "Const Medidor",
        "energia_geracao_kwh",
        "Medidor",
    ],
}

# Grandeza filtrada na aba medicao_resumida e o novo nome da coluna de consumo.
MEDICAO_RESUMIDA_GRANDEZA = "ENERGIA GERAÇÃO - KWH"
MEDICAO_RESUMIDA_COL = "energia_geracao_kwh"

# 'id_uc_normalizado' aparece SEMPRE logo após 'id_uc', em todas as abas que têm
# id_uc. 'item_normalizado' aparece logo após 'item' na aba itens_fatura.
for _cols in CANONICAL_COLUMNS.values():
    if "id_uc" in _cols and "id_uc_normalizado" not in _cols:
        _cols.insert(_cols.index("id_uc") + 1, "id_uc_normalizado")
_itf = CANONICAL_COLUMNS["itens_fatura"]
if "item" in _itf and "item_normalizado" not in _itf:
    _itf.insert(_itf.index("item") + 1, "item_normalizado")

# Colunas que NUNCA devem ser removidas pelo "descarte de colunas 100% nulas",
# mesmo que venham vazias (mantêm o significado da linha).
COLS_PROTEGIDAS = {
    "id_fatura",
    "numero_fatura",
    "arquivo_pdf",
    "fornecedor",
    "id_uc",
    "id_uc_normalizado",
    "item_normalizado",
    "competencia",
    "demanda_contratada_kw",
    "demanda_geracao_contratada_kw",
    "scee_geracao_ciclo",
    "scee_saldo_kwh_total",
    "scee_saldo_kwh_P",
    "scee_saldo_kwh_FP",
    "scee_saldo_kwh_HR",
    "energia_geracao_kwh",
}

# Chave usada para casar a mesma fatura entre planilha antiga e novas faturas
# (evita duplicar uma fatura já existente ao concatenar). Vale por aba.
DEDUP_KEYS = {
    "fatura":           ["id_fatura"],
    "cliente":          ["id_uc"],
    "impostos":         ["id_fatura", "Tributo"],
    "fatura_resumida":  ["id_fatura"],
}

# Abas em que a deduplicação (na concatenação) considera a LINHA INTEIRA, não uma
# chave de colunas: itens/medição podem repetir legitimamente o conjunto-chave no
# mês (ex.: variações de leitura); só linhas 100% idênticas são removidas.
DEDUP_FULL_ROW = {"itens_fatura", "medicao", "medicao_resumida"}

# Nome da aba oculta onde gravamos os metadados (mapa nome_exibido -> canônico).
META_SHEET = "_faturas_meta"

# Apelidos conhecidos: nome (normalizado) que costuma aparecer em planilhas
# antigas -> coluna canônica correspondente. Usado no auto-match quando não há
# metadados embutidos. (O 'link_pdf' das planilhas do Colab casa diretamente com
# a coluna canônica 'link_pdf' por nome exato; aqui ficam só variações.)
COLUMN_ALIASES = {
    "fatura": {
        "link": "link_pdf",
        "urlpdf": "link_pdf",
        "url": "link_pdf",
    },
}


def default_display_names() -> dict[str, dict[str, str]]:
    """Mapa {aba: {canonico: nome_exibido_padrao}} — por padrão, idênticos."""
    return {
        aba: {c: c for c in cols}
        for aba, cols in CANONICAL_COLUMNS.items()
    }


def all_canonical(aba: str) -> list[str]:
    return list(CANONICAL_COLUMNS.get(aba, []))
