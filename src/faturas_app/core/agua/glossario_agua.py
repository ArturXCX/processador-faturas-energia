"""Glossário da planilha de ÁGUA (aba `glossario`): abas, colunas, valores, regras de validação e conceitos."""
from __future__ import annotations

from . import schema_agua as S
from .derivados_agua import REGRAS

NOME_ABA = "glossario"

ABAS_DOC = [
    (S.ABA_FATURAS, "Uma linha por fatura individual de qualquer concessionária (SAE, DEMAE, SAAEs, SANESC, São Simão, "
                    "Ipameri, Buriti Alegre, CODEGO) OU por conta da fatura ANALÍTICA da Saneago (origem = analitica). "
                    "Todas as concessionárias usam as mesmas colunas; o que não é impresso fica vazio."),
    (S.ABA_ITENS, "Lançamentos impressos na fatura (tarifa de água, esgoto, taxas, IRPJ…): várias linhas por fatura, "
                  "com a categoria de valor usada nas somas."),
    (S.ABA_HISTORICO, "Histórico de consumo impresso na fatura (6 a 12 meses anteriores): uma linha por mês."),
    (S.ABA_BORDEROS, "Borderôs da Saneago (fatura agrupada do órgão): uma linha por Nº de fatura, com os totais impressos, "
                     "a base de cálculo, a retenção de IRPJ e o valor final pago."),
    (S.ABA_CONTAS_BORDERO, "Contas listadas dentro de cada borderô da Saneago (valor BRUTO por conta: água, esgoto, SMRSU)."),
    (S.ABA_VALIDACAO, "Ocorrências das regras de validação (erro / aviso / info), uma por linha, com o id da fatura ou borderô."),
    (S.ABA_MAPA, "Cadastro de contas (mapa de contas): uma linha por conta real com fornecedor, unidade institucional e serviços."),
]

COLUNAS_DOC = [
    (S.ABA_FATURAS, "id_fatura_agua", "Identificador: <FORNECEDOR>_<nº da fatura>; sem número impresso: <FORNECEDOR>_<conta>_<AAAA-MM>."),
    (S.ABA_FATURAS, "fornecedor", "Concessionária (SANEAGO, SAE_CATALAO, DEMAE_CALDAS_NOVAS, DEMAE_PANAMA, SAAE_ABADIANIA, SAAE_CORUMBA, "
                                  "SAAE_LEOPOLDO_BULHOES, SAAE_MINEIROS, SANESC, SAO_SIMAO_SA, AGUAS_IPAMERI, BURITI_ALEGRE_AMBIENTAL, CODEGO)."),
    (S.ABA_FATURAS, "cnpj_fornecedor", "CNPJ da concessionária (só dígitos)."),
    (S.ABA_FATURAS, "numero_fatura", "Número da fatura/guia como impresso (sem prefixo). Vazio quando a concessionária não numera (SANESC)."),
    (S.ABA_FATURAS, "arquivo_pdf", "Nome do arquivo PDF de origem."),
    (S.ABA_FATURAS, "link_pdf", "Link para o PDF (busca no Google Drive pelo nome do arquivo ou modelo configurado)."),
    (S.ABA_FATURAS, "conta", "Conta / matrícula / cadastro / ligação em dígitos, INCLUINDO o dígito verificador quando impresso (1627885-2 → 16278852)."),
    (S.ABA_FATURAS, "conta_formatada", "A conta como impressa (1627885 2, 9945-7, 0001255.2, 000007155…)."),
    (S.ABA_FATURAS, "conta_canonica", "Conta pelo mapa de contas (dígitos sem zeros à esquerda); sem mapa, os dígitos da própria conta."),
    (S.ABA_FATURAS, "unidade_institucional", "Unidade (fórum, juizado, prédio) pelo mapa de contas."),
    (S.ABA_FATURAS, "hidrometro", "Número do hidrômetro impresso."),
    (S.ABA_FATURAS, "nome_cliente", "Nome do titular/cliente impresso."),
    (S.ABA_FATURAS, "logradouro", "Endereço da ligação impresso."),
    (S.ABA_FATURAS, "competencia", "Mês/ano de referência impresso na fatura (AAAA-MM). Na SAAE Abadiânia é o 'MÊS FAT.' (mês de faturamento)."),
    (S.ABA_FATURAS, "data_emissao", "Data de emissão (AAAA-MM-DD), quando impressa."),
    (S.ABA_FATURAS, "data_vencimento", "Data de vencimento (AAAA-MM-DD)."),
    (S.ABA_FATURAS, "data_leitura_anterior", "Data da leitura anterior do hidrômetro."),
    (S.ABA_FATURAS, "data_leitura_atual", "Data da leitura atual do hidrômetro."),
    (S.ABA_FATURAS, "leitura_anterior", "Leitura anterior (m³ acumulados)."),
    (S.ABA_FATURAS, "leitura_atual", "Leitura atual (m³ acumulados)."),
    (S.ABA_FATURAS, "consumo_m3", "Consumo medido no mês (m³) — leitura atual − anterior, ou o consumo impresso."),
    (S.ABA_FATURAS, "consumo_faturado_m3", "Consumo cobrado (m³): pode ser o mínimo, a média ou estimativa quando não há leitura."),
    (S.ABA_FATURAS, "tipo_consumo", "Como o consumo foi apurado: Medido, Mínimo, Lido, Estimado, 1-Medido, LEITURA NORMAL…"),
    (S.ABA_FATURAS, "categoria", "Categoria da ligação: PUB (pública), COM, RES, IND, PUBLICA, Comercial…"),
    (S.ABA_FATURAS, "dias", "Dias do período de consumo."),
    (S.ABA_FATURAS, "valor_agua", "Soma dos lançamentos de ÁGUA (tarifa de água, custo mínimo de água, captação/distribuição)."),
    (S.ABA_FATURAS, "valor_esgoto", "Soma dos lançamentos de ESGOTO (coleta, afastamento, tratamento, custo mínimo de esgoto)."),
    (S.ABA_FATURAS, "valor_taxas", "Soma de taxas, tarifas fixas/básicas, resíduos sólidos (SMRSU/lixo) e retenções (IRPJ negativo)."),
    (S.ABA_FATURAS, "valor_multa_juros", "Multa, juros, mora e atualização monetária."),
    (S.ABA_FATURAS, "valor_total", "Total a pagar impresso na fatura."),
    (S.ABA_FATURAS, "soma_itens", "Soma de todos os lançamentos lidos (deve bater com valor_total — regra ITENS_NAO_FECHAM)."),
    (S.ABA_FATURAS, "origem", "fatura (documento individual) ou analitica (bloco da fatura analítica da Saneago)."),
    (S.ABA_FATURAS, "extraido_por_ocr", "True quando o PDF era imagem e o texto veio do OCR."),
    (S.ABA_FATURAS, "observacao", "Anotações do extrator (código de baixa, órgão pagador, consumo estimado, parcialidade do OCR)."),
    (S.ABA_ITENS, "ordem", "Posição do lançamento na fatura."),
    (S.ABA_ITENS, "codigo", "Código do lançamento quando impresso (104, 1146, 001…)."),
    (S.ABA_ITENS, "descricao", "Descrição como impressa."),
    (S.ABA_ITENS, "descricao_normalizada", "Descrição sem acento/código, em maiúsculas, para agrupar."),
    (S.ABA_ITENS, "categoria_valor", "agua | esgoto | taxas | multa_juros | credito | outros — categoria usada nas somas da fatura."),
    (S.ABA_ITENS, "valor", "Valor do lançamento (negativo para retenções e créditos)."),
    (S.ABA_HISTORICO, "competencia_fatura", "Competência da fatura em que o histórico foi impresso."),
    (S.ABA_HISTORICO, "competencia", "Mês do histórico (AAAA-MM)."),
    (S.ABA_HISTORICO, "consumo_m3", "Consumo daquele mês (m³)."),
    (S.ABA_HISTORICO, "valor", "Valor daquele mês, quando impresso (analítica Saneago)."),
    (S.ABA_HISTORICO, "tipo", "Tipo de apuração daquele mês (Lido, Mínimo…), quando impresso."),
    (S.ABA_BORDEROS, "id_bordero_agua", "SANEAGO_<nº da fatura agrupada>."),
    (S.ABA_BORDEROS, "cod_agrupador / cod_pagador", "Códigos do órgão agrupador e do órgão pagador (TJGO = 2130)."),
    (S.ABA_BORDEROS, "quantidade_contas", "Quantidade de contas agrupadas impressa."),
    (S.ABA_BORDEROS, "quantidade_contas_extraidas", "Quantidade de contas que o extrator conseguiu ler."),
    (S.ABA_BORDEROS, "valor_agua / valor_esgoto / valor_smrsu", "Totais impressos por coluna (formato novo) ou água/esgoto (formato antigo)."),
    (S.ABA_BORDEROS, "base_calculo", "Base de cálculo do IRPJ impressa (água + esgoto)."),
    (S.ABA_BORDEROS, "aliquota_irpj", "Alíquota de IRPJ retido (4,80 %)."),
    (S.ABA_BORDEROS, "valor_retido", "Imposto retido (água e esgoto)."),
    (S.ABA_BORDEROS, "valor_final", "VALOR FINAL DA FATURA — o que é efetivamente pago (bruto − retido)."),
    (S.ABA_BORDEROS, "soma_valores_extraidos", "Soma das contas extraídas (bruto); comparada com o total impresso."),
    (S.ABA_BORDEROS, "bate_total", "SIM / NÃO / N/A — a soma das contas confere com o total impresso?"),
    (S.ABA_BORDEROS, "formato", "antigo (CONSUMO ÁGUA · VALOR · CONSUMO ESGOTO · VALOR) ou novo (CONSUMO · ÁGUA · ESGOTO · SMRSU)."),
    (S.ABA_BORDEROS, "escaneado", "SIM quando o PDF era imagem (contas lidas por OCR)."),
    (S.ABA_CONTAS_BORDERO, "valor_total", "Valor BRUTO da conta no borderô (água + esgoto + SMRSU), antes da retenção."),
    (S.ABA_VALIDACAO, "gravidade", "erro (impede a confiança no dado), aviso (conferir) ou info (só registro)."),
    (S.ABA_VALIDACAO, "regra", "Código da regra (ver categoria 'Regra de validação')."),
    (S.ABA_MAPA, "identificadores", "Todas as formas em que a conta apareceu impressa."),
    (S.ABA_MAPA, "agua / esgoto / smrsu", "Serviços cobrados nessa conta (True/False)."),
    (S.ABA_MAPA, "operante", "Conta ativa (False quando encerrada / imóvel devolvido)."),
]

VALORES_DOC = [
    ("SANEAGO borderô", "Fatura AGRUPADA do órgão público: várias contas num documento; retenção de IRPJ de 4,80 % sobre "
                        "água + esgoto no nível da fatura. Os valores por conta são BRUTOS."),
    ("SANEAGO analítica", "Fatura analítica de órgão público: um bloco por conta (hidrômetro, leituras, lançamentos, histórico)."),
    ("SMRSU", "Serviço de Manejo de Resíduos Sólidos Urbanos — taxa de lixo cobrada junto da conta de água (Saneago, formato novo)."),
    ("IRPJ (retenção)", "Imposto de renda retido na fonte pelo órgão pagador (4,80 %); aparece negativo nos itens de algumas concessionárias."),
    ("Competência (AAAA-MM)", "Mês de referência impresso na fatura, ex.: 2025-04 = abril/2025."),
    ("agua / esgoto / taxas / multa_juros / credito / outros", "Categorias de valor dos lançamentos; taxas inclui tarifas fixas/básicas, "
        "resíduos sólidos, serviços avulsos e retenções (IRPJ)."),
]

REGRAS_VALIDACAO_DOC = [(k, f"{v[0]}: {v[1]}") for k, v in REGRAS.items()]

CONCEITOS = [
    ("Hidrômetro", "Medidor de volume de água da ligação; a leitura é acumulada em m³."),
    ("Consumo mínimo / tarifa mínima", "Volume ou valor cobrado mesmo sem consumo medido (franquia da categoria)."),
    ("Consumo estimado / média", "Consumo apurado sem leitura (média dos últimos meses), depois compensado."),
    ("Categoria pública", "Tarifa aplicada a órgãos públicos (PUB / PUBLICA)."),
    ("Órgão agrupador / pagador", "Na Saneago, o órgão que agrupa várias contas num borderô (agrupador) e o que paga (pagador)."),
    ("Mapa de contas", "Cadastro que liga cada conta impressa à unidade institucional; substitui o contas.json do projeto original."),
]


def construir_glossario_df():
    import pandas as pd
    rows = []
    for termo, defin in ABAS_DOC:
        rows.append((termo, "Aba da planilha", defin))
    for aba, col, defin in COLUNAS_DOC:
        rows.append((col, f"Coluna · {aba}", defin))
    for termo, defin in VALORES_DOC:
        rows.append((termo, "Valor / categoria", defin))
    for termo, defin in REGRAS_VALIDACAO_DOC:
        rows.append((termo, "Regra de validação", defin))
    for termo, defin in CONCEITOS:
        rows.append((termo, "Conceito geral", defin))
    return pd.DataFrame(rows, columns=["Termo", "Categoria", "Definição"])


def garantir_glossario(dfs: dict) -> dict:
    if any(str(k).lower().startswith("gloss") for k in dfs):
        return dfs
    novo = dict(dfs)
    novo[NOME_ABA] = construir_glossario_df()
    return novo
