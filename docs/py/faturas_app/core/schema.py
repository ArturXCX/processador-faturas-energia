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
BASE_SHEETS = ["fatura", "unidade_consumidora", "itens_fatura", "impostos", "medicao"]

# Abas DERIVADAS (calculadas a partir das base em Dataset.to_dataframes).
DERIVED_SHEETS = ["fatura_resumida", "medicao_resumida", "tarifas"]

# Ordem das abas na planilha de saída (resumidas posicionadas como pedido).
SHEET_ORDER = ["fatura_resumida", "fatura", "unidade_consumidora", "itens_fatura",
               "tarifas", "impostos", "medicao", "medicao_resumida"]

# Cores (cabeçalho, linha alternada) — mesmas dos notebooks.
SHEET_COLORS = {
    "fatura":       ("1F4E79", "BDD7EE"),
    "unidade_consumidora": ("1F4E79", "BDD7EE"),
    "itens_fatura": ("375623", "E2EFDA"),
    "tarifas":      ("7F6000", "FFF2CC"),
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
# 'unidade_consumidora'); 'link_pdf' guarda o link do PDF (busca no Drive pelo
# nome do arquivo).
CANONICAL_COLUMNS = {
    "fatura": [
        "id_fatura",
        "numero_fatura",
        "arquivo_pdf",
        "link_pdf",
        "fornecedor",
        "id_uc",
        "medidor",
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
    # Três blocos, nesta ordem: identidade extraída do PDF (razao_social..uf),
    # cadastro vindo do dicionário oficial de UCs (core/dicionario_uc.py) e os
    # agregados calculados em derivados.py (primeira/ultima_*).
    "unidade_consumidora": [
        "id_uc",
        "razao_social",
        "cnpj",
        "cep",
        "municipio",
        "uf",
        "id_uc_dicionario",
        "id_uc_dicionario_sem_format",
        "id_uc_antigo_dicionario",
        "id_uc_aneel_bordero",
        "uc_operante",
        "medidores_utilizados_dicionario",
        "medidor_atual_dicionario",
        "unidade_judiciaria",
        "uj_uc_at_bt_gd",
        "concessionaria",
        "endereco_dicionario",
        "comarca",
        "grupo_fornecimento_at_bt",
        "limite_fornecimento_tensao",
        "possui_geracao_distribuida",
        "participa_rateio",
        "e_gerador_rateio",
        "e_beneficiaria_rateio",
        "rateio_comum",
        "rateio_ufv_cachoeira_dourada",
        "percentual_rateio",
        "demanda_alterada",
        "demanda_futura_kw",
        "protocolo_alteracao_demanda",
        "saldo_scee_cadastro_kwh",
        "prioridade_rateio",
        "gd_sem_rateio",
        "usina_fotovoltaica_cachoeira_dourada",
        "primeira_competencia",
        "ultima_competencia",
        "primeira_fatura",
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
        "medidor",
        "competencia",
        "valor_total_r$",
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
    # Tabela de REFERÊNCIA (não tem id_fatura nem id_uc): 1 linha por
    # (fornecedor, item, tarifa_unitaria_r$), na competência em que essa
    # combinação apareceu pela primeira vez. Ver derivados._derivar_tarifas.
    "tarifas": [
        "fornecedor",
        "competencia",
        "item",
        "tipo",
        "unidade",
        "preco_unitario_com_tributos_r$",
        "tarifa_unitaria_r$",
        "item_normalizado",
    ],
}

# Grandeza filtrada na aba medicao_resumida e o novo nome da coluna de consumo.
MEDICAO_RESUMIDA_GRANDEZA = "ENERGIA GERAÇÃO - KWH"
MEDICAO_RESUMIDA_COL = "energia_geracao_kwh"

# Colunas auxiliares de id_uc, inseridas logo após 'id_uc':
#  - Na aba 'unidade_consumidora' (cadastro por UC): as três colunas completas
#    'id_uc_sem_format', 'id_uc_atual_medidor', 'id_uc_atual_medidor_sem_format'.
#  - Nas demais abas: apenas 'id_uc_atual' (que carrega o valor de
#    id_uc_atual_medidor SEM formatação — o antigo 'id_uc_atual_medidor_sem_format').
# 'id_uc_canonico' fecha os dois blocos e aparece em TODAS as abas com id_uc: é
# a UC do dicionário oficial (que não sofre com troca de medidor nem com mudança
# de formato do id_uc) e cai para a heurística de medidor quando o dicionário
# não conhece a UC. Ver core/dicionario_uc.py e derivados._enriquecer_dicionario_uc.
# 'item_normalizado' aparece logo após 'item' na aba itens_fatura.
_EXTRAS_ID_UC_UC = ["id_uc_sem_format", "id_uc_atual_medidor",
                    "id_uc_atual_medidor_sem_format", "id_uc_canonico"]
_EXTRAS_ID_UC_OUTRAS = ["id_uc_atual", "id_uc_canonico"]
for _aba, _cols in CANONICAL_COLUMNS.items():
    if "id_uc" not in _cols:
        continue
    _idx = _cols.index("id_uc")
    _extras = _EXTRAS_ID_UC_UC if _aba == "unidade_consumidora" else _EXTRAS_ID_UC_OUTRAS
    for _i, _novo in enumerate(_extras, start=1):
        if _novo not in _cols:
            _cols.insert(_idx + _i, _novo)
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
    "id_uc_sem_format",
    "id_uc_atual_medidor",
    "id_uc_atual_medidor_sem_format",
    "id_uc_atual",
    "id_uc_canonico",
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
    # Cadastro vindo do dicionário oficial de UCs: protegidas para o formato da
    # aba ficar estável entre lotes (um lote pequeno pode não ter nenhuma UC com
    # rateio, por exemplo, e a coluna sairia vazia — mas precisa continuar lá
    # para o remapeamento por metadados na concatenação).
    "id_uc_dicionario",
    "id_uc_dicionario_sem_format",
    "id_uc_antigo_dicionario",
    "id_uc_aneel_bordero",
    "uc_operante",
    "medidores_utilizados_dicionario",
    "medidor_atual_dicionario",
    "unidade_judiciaria",
    "uj_uc_at_bt_gd",
    "concessionaria",
    "endereco_dicionario",
    "comarca",
    "grupo_fornecimento_at_bt",
    "limite_fornecimento_tensao",
    "possui_geracao_distribuida",
    "participa_rateio",
    "e_gerador_rateio",
    "e_beneficiaria_rateio",
    "rateio_comum",
    "rateio_ufv_cachoeira_dourada",
    "percentual_rateio",
    "demanda_alterada",
    "demanda_futura_kw",
    "protocolo_alteracao_demanda",
    "saldo_scee_cadastro_kwh",
    "prioridade_rateio",
    "gd_sem_rateio",
    "usina_fotovoltaica_cachoeira_dourada",
}

# Chave usada para casar a mesma fatura entre planilha antiga e novas faturas
# (evita duplicar uma fatura já existente ao concatenar). Vale por aba.
#
# 'tarifas' NÃO entra aqui de propósito: é reinstalada inteira (recalculada do
# zero sobre o conjunto completo) em derivados.aplicar_concat, como
# 'unidade_consumidora' — a regra "mantém a competência mais antiga" só fecha
# olhando todas as faturas de uma vez.
#
# TODO (decidido para depois): 'unidade_consumidora' continua deduplicando por
# 'id_uc', não por 'id_uc_canonico'. Migrar corrigiria a fragmentação de UCs que
# mudaram de formato no meio do histórico, mas mudaria a CONTAGEM de linhas de
# planilhas já publicadas/usadas em dashboards. 'id_uc_canonico' fica disponível
# como coluna para quem quiser agrupar manualmente.
DEDUP_KEYS = {
    "fatura":               ["id_fatura"],
    "unidade_consumidora":  ["id_uc"],
    "impostos":             ["id_fatura", "Tributo"],
    "fatura_resumida":      ["id_fatura"],
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
