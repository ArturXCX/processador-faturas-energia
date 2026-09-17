"""Esquema canônico das abas/tabelas de ÁGUA — o mesmo para TODAS as concessionárias.

Cada extrator devolve linhas nestas colunas; o que uma concessionária não imprime fica vazio. Assim SAE Catalão, DEMAE,
SAAEs, SANESC, São Simão, Ipameri, Buriti Alegre, CODEGO e a Saneago (borderô e analítica) convivem nas mesmas abas da
planilha e nas mesmas tabelas do banco, diferenciadas pela coluna `fornecedor`.
"""
from __future__ import annotations

# ── fornecedores (valores da coluna `fornecedor`) ─────────────────────────────
FORNECEDORES = {
    "SANEAGO":                 dict(nome="Saneamento de Goiás S.A. (SANEAGO)", cnpj="01616929000102", cidade="Goiânia"),
    "SAE_CATALAO":             dict(nome="Superintendência Municipal de Água e Esgoto de Catalão (SAE)", cnpj="04750108000152", cidade="Catalão"),
    "DEMAE_CALDAS_NOVAS":      dict(nome="Departamento Municipal de Água e Esgoto de Caldas Novas (DEMAE)", cnpj="00675468000186", cidade="Caldas Novas"),
    "DEMAE_PANAMA":            dict(nome="Departamento Municipal de Água e Esgoto de Panamá (DEMAEP)", cnpj="00079830000156", cidade="Panamá"),
    "SAAE_ABADIANIA":          dict(nome="Serviço Autônomo de Água e Esgoto de Abadiânia (SAAE)", cnpj="24836603000196", cidade="Abadiânia"),
    "SAAE_CORUMBA":            dict(nome="Serviço Autônomo de Água e Esgoto de Corumbá de Goiás (SAAE)", cnpj="02033679000140", cidade="Corumbá de Goiás"),
    "SAAE_LEOPOLDO_BULHOES":   dict(nome="Serviço Autônomo de Água e Esgoto de Leopoldo de Bulhões (SAAE)", cnpj="44621400000190", cidade="Leopoldo de Bulhões"),
    "SAAE_MINEIROS":           dict(nome="Serviço Autônomo de Água e Esgoto de Mineiros (SAAE)", cnpj="02316487000141", cidade="Mineiros"),
    "SANESC":                  dict(nome="Agência de Saneamento de Senador Canedo (SANESC)", cnpj="37426889000183", cidade="Senador Canedo"),
    "SAO_SIMAO_SA":            dict(nome="São Simão Saneamento Ambiental", cnpj="46572336000120", cidade="São Simão"),
    "AGUAS_IPAMERI":           dict(nome="Águas de Ipameri", cnpj="43547497000175", cidade="Ipameri"),
    "BURITI_ALEGRE_AMBIENTAL": dict(nome="Buriti Alegre Ambiental", cnpj="43390208000177", cidade="Buriti Alegre"),
    "CODEGO":                  dict(nome="Companhia de Desenvolvimento Econômico de Goiás (CODEGO)", cnpj="", cidade="Goiânia"),
}

# ── abas / tabelas ────────────────────────────────────────────────────────────
ABA_FATURAS = "fatura_agua"
ABA_ITENS = "itens_agua"
ABA_HISTORICO = "historico_agua"
ABA_BORDEROS = "borderos_agua"
ABA_CONTAS_BORDERO = "contas_bordero_agua"
ABA_VALIDACAO = "validacao_agua"
ABA_MAPA = "mapa_contas_agua"
SHEET_ORDER = [ABA_FATURAS, ABA_ITENS, ABA_HISTORICO, ABA_BORDEROS, ABA_CONTAS_BORDERO, ABA_VALIDACAO, ABA_MAPA]

SHEET_COLORS = {
    ABA_FATURAS:        ("1F4E79", "BDD7EE"),
    ABA_ITENS:          ("375623", "E2EFDA"),
    ABA_HISTORICO:      ("4A235A", "E8D5F5"),
    ABA_BORDEROS:       ("1F4E79", "BDD7EE"),
    ABA_CONTAS_BORDERO: ("375623", "E2EFDA"),
    ABA_VALIDACAO:      ("9C0006", "FFC7CE"),
    ABA_MAPA:           ("7F6000", "FFF2CC"),
    "glossario":        ("0E6E63", "D6EFEC"),
}

# Uma linha por FATURA INDIVIDUAL (qualquer concessionária) ou por conta da fatura analítica da Saneago.
FATURA_COLS = [
    "id_fatura_agua",          # <FORNECEDOR>_<nº da fatura>; sem número: <FORNECEDOR>_<conta>_<AAAA-MM>
    "fornecedor",
    "cnpj_fornecedor",
    "numero_fatura",
    "arquivo_pdf",
    "link_pdf",
    "conta",                   # só dígitos (matrícula/conta+DV/cadastro), como impresso, sem pontuação
    "conta_formatada",         # como impresso (1627885 2, 9945-7, 0001255.2 …)
    "conta_canonica",          # pelo mapa de contas (derivados_agua); cai para `conta`
    "unidade_institucional",   # do mapa de contas
    "hidrometro",
    "nome_cliente",
    "logradouro",
    "competencia",             # AAAA-MM
    "data_emissao",
    "data_vencimento",
    "data_leitura_anterior",
    "data_leitura_atual",
    "leitura_anterior",
    "leitura_atual",
    "consumo_m3",              # consumo medido (leitura atual − anterior) quando impresso
    "consumo_faturado_m3",     # consumo cobrado (mínimo, estimado, médio…)
    "tipo_consumo",            # Medido, Mínimo, Médio, Estimado, Informado, Normal…
    "categoria",               # PUBLICA, COMERCIAL, RES…
    "dias",
    "valor_agua",
    "valor_esgoto",
    "valor_taxas",             # SMRSU / resíduos sólidos / tarifa básica / outras taxas
    "valor_multa_juros",
    "valor_total",
    "soma_itens",              # soma dos lançamentos (para a validação)
    "origem",                  # fatura | analitica
    "extraido_por_ocr",
    "observacao",
]

# Uma linha por LANÇAMENTO impresso (itens da fatura). Preenchida pelas concessionárias que discriminam os itens.
ITEM_COLS = [
    "id_fatura_agua", "fornecedor", "conta", "conta_canonica", "competencia",
    "ordem", "codigo", "descricao", "descricao_normalizada", "categoria_valor", "valor",
]

# Uma linha por MÊS do histórico de consumo impresso na fatura (6 a 12 meses).
HISTORICO_COLS = [
    "id_fatura_agua", "fornecedor", "conta", "conta_canonica", "competencia_fatura",
    "competencia", "consumo_m3", "valor", "tipo",
]

# Uma linha por BORDERÔ (fatura agrupada da Saneago: várias contas, retenção no nível da fatura).
BORDERO_COLS = [
    "id_bordero_agua",         # SANEAGO_<nº da fatura>
    "fornecedor",
    "numero_fatura",
    "arquivo_pdf",
    "cod_agrupador",
    "cod_pagador",
    "nome_agrupador",
    "competencia",
    "data_emissao",
    "data_vencimento",
    "quantidade_contas",           # impressa ("QUANTIDADE DE CONTAS AGRUPADAS")
    "quantidade_contas_extraidas",
    "consumo_total_m3",
    "valor_agua",
    "valor_esgoto",
    "valor_smrsu",
    "base_calculo",                # água + esgoto (base do IRPJ), impressa
    "aliquota_irpj",
    "valor_retido",
    "valor_final",                 # o que é pago
    "soma_valores_extraidos",      # soma das contas extraídas (bruto)
    "bate_total",                  # SIM / NÃO / N/A
    "formato",                     # antigo (2 colunas de valor) | novo (ÁGUA/ESGOTO/SMRSU)
    "escaneado",
    "extraido_por_ocr",
    "observacao",
]

# Uma linha por CONTA dentro do borderô.
CONTA_BORDERO_COLS = [
    "id_bordero_agua", "fornecedor", "competencia", "ordem",
    "conta", "conta_formatada", "conta_canonica", "unidade_institucional",
    "nome_cliente", "logradouro", "consumo_m3", "valor_agua", "valor_esgoto", "valor_smrsu", "valor_total",
]

VALIDACAO_COLS = ["id", "fornecedor", "conta", "conta_canonica", "competencia", "gravidade", "regra", "detalhe"]

# Mapa de contas (cadastro): uma linha por conta real.
MAPA_COLS = [
    "conta_canonica", "identificadores", "fornecedor", "unidade_institucional", "cidade", "nome_cliente",
    "logradouro", "hidrometro", "agua", "esgoto", "smrsu", "operante", "primeira_competencia", "ultima_competencia",
    "faturas", "origem",
]

CANONICAL_COLUMNS = {
    ABA_FATURAS: FATURA_COLS,
    ABA_ITENS: ITEM_COLS,
    ABA_HISTORICO: HISTORICO_COLS,
    ABA_BORDEROS: BORDERO_COLS,
    ABA_CONTAS_BORDERO: CONTA_BORDERO_COLS,
    ABA_VALIDACAO: VALIDACAO_COLS,
    ABA_MAPA: MAPA_COLS,
}

# Chave de deduplicação por aba (concatenação e carga no banco).
DEDUP_KEYS = {
    ABA_FATURAS: ["id_fatura_agua"],
    ABA_BORDEROS: ["id_bordero_agua"],
    ABA_MAPA: ["conta_canonica"],
}
DEDUP_FULL_ROW = {ABA_ITENS, ABA_HISTORICO, ABA_CONTAS_BORDERO, ABA_VALIDACAO}

COLUNAS_NUMERICAS = {
    ABA_FATURAS: ["leitura_anterior", "leitura_atual", "consumo_m3", "consumo_faturado_m3", "dias", "valor_agua",
                  "valor_esgoto", "valor_taxas", "valor_multa_juros", "valor_total", "soma_itens"],
    ABA_ITENS: ["ordem", "valor"],
    ABA_HISTORICO: ["consumo_m3", "valor"],
    ABA_BORDEROS: ["quantidade_contas", "quantidade_contas_extraidas", "consumo_total_m3", "valor_agua", "valor_esgoto",
                   "valor_smrsu", "base_calculo", "aliquota_irpj", "valor_retido", "valor_final", "soma_valores_extraidos"],
    ABA_CONTAS_BORDERO: ["ordem", "consumo_m3", "valor_agua", "valor_esgoto", "valor_smrsu", "valor_total"],
}

# Categorias de valor dos lançamentos (para somar água/esgoto/taxas a partir dos itens).
CATEGORIAS_VALOR = ("agua", "esgoto", "taxas", "multa_juros", "outros", "credito")


def linha_vazia(aba: str) -> dict:
    return {c: None for c in CANONICAL_COLUMNS[aba]}
