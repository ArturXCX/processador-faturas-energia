"""
Glossário da planilha de faturas.

Combina três fontes:
  1. ABAS_DOC / COLUNAS_DOC / VALORES_DOC — documentação de COMO este app nomeia
     as abas, colunas e valores (o "como as informações são nomeadas e seus
     valores", pedido no requisito).
  2. CONCEITOS — termos gerais de conta de energia (baseados no glossário oficial
     da Equatorial: go.equatorialenergia.com.br/sua-conta/glossario/).
  3. resources/glossario_itens.json — 301 descrições de itens de faturamento
     extraídas do glossário oficial em PDF (itens da aba `itens_fatura`).

`construir_glossario_df()` monta a aba `glossario`; `garantir_glossario()` a
acrescenta a um conjunto de abas apenas se ainda não existir.
"""
from __future__ import annotations

import json
import unicodedata
from pathlib import Path

import pandas as pd

NOME_ABA = "glossario"
_RES = Path(__file__).resolve().parent.parent / "resources"


# ──────────────────────────────────────────────────────────────────────────────
# 1. Documentação das ABAS
# ──────────────────────────────────────────────────────────────────────────────
ABAS_DOC = [
    ("fatura", "Uma linha por fatura: identificação, datas, valor total, dados "
               "fiscais (NF-e), classificação tarifária e leituras."),
    ("unidade_consumidora", "Dados cadastrais da Unidade Consumidora (razão "
                            "social, CNPJ, endereço, primeira/última "
                            "competência e fatura). Uma linha por UC."),
    ("itens_fatura", "Itens que compõem a fatura (energia, demanda, tributos, "
                     "ajustes). Várias linhas por fatura; ver categoria 'Item de fatura'."),
    ("tarifas", "Tabela de referência: para cada combinação de fornecedor+item+"
                "tarifa observada em 'itens_fatura', a competência em que essa "
                "combinação apareceu pela primeira vez (bandeira tarifária e "
                "itens sem tarifa ficam de fora)."),
    ("impostos", "Tributos incidentes (PIS/PASEP, COFINS, ICMS) com base de "
                 "cálculo, alíquota e valor."),
    ("medicao", "Grandezas medidas (energia ativa, demanda, etc.) por posto "
                "horário, com leituras e consumo."),
    ("fatura_resumida", "Versão enxuta da aba 'fatura' (primeira aba): "
                        "identificação, medidor, valor total, classificação, "
                        "demandas, SCEE e dias de leitura."),
    ("medicao_resumida", "Versão da aba 'medicao' filtrada só na grandeza "
                         "'ENERGIA GERAÇÃO - KWH', com 'Consumo kWh' renomeado para "
                         "'energia_geracao_kwh'."),
    ("glossario", "Esta aba: significado das colunas, valores e itens da fatura."),
]


# ──────────────────────────────────────────────────────────────────────────────
# 2. Documentação das COLUNAS (por aba)
# ──────────────────────────────────────────────────────────────────────────────
COLUNAS_DOC = [
    # fatura
    ("fatura", "id_fatura", "Identificador da fatura com prefixo da fornecedora "
               "(ex.: EQUATORIAL_10001867464, CHESP_1510617). Usado para ligar as abas."),
    ("fatura", "numero_fatura", "Número da fatura SEM o prefixo (valor original, "
               "ex.: 10001867464). Para Equatorial corresponde ao nome do PDF no Drive."),
    ("fatura", "arquivo_pdf", "Nome do arquivo PDF de origem."),
    ("fatura", "link_pdf", "Link para o PDF (busca no Google Drive pelo nome do arquivo "
               "ou modelo de URL configurado no app)."),
    ("fatura", "fornecedor", "Distribuidora de origem: EQUATORIAL ou CHESP."),
    ("fatura", "id_uc", "Código da Unidade Consumidora (UC)."),
    ("fatura / fatura_resumida", "medidor", "Número de série do medidor da UC "
               "nesta fatura (moda dos medidores da aba 'medicao')."),
    ("fatura", "data_emissao", "Data de emissão da fatura (formato AAAA-MM-DD)."),
    ("fatura", "competencia", "Mês de referência do consumo (formato AAAA-MM)."),
    ("fatura", "data_vencimento", "Data de vencimento da fatura (AAAA-MM-DD)."),
    ("fatura", "valor_total_r$", "Valor total a pagar, em reais."),
    ("fatura", "numero_nf", "Número da Nota Fiscal."),
    ("fatura", "serie_nf", "Série da Nota Fiscal."),
    ("fatura", "cfop", "Código Fiscal de Operações e Prestações (ex.: 5258)."),
    ("fatura", "chave_acesso_nfe", "Chave de acesso da NF-e (44 dígitos)."),
    ("fatura", "protocolo_autorizacao", "Protocolo de autorização da NF-e."),
    ("fatura", "data_hora_protocolo", "Data e hora do protocolo de autorização da NF-e."),
    ("fatura", "classificacao_tarifaria", "Classe/subgrupo tarifário da UC (ex.: A4, B3, "
               "Poder Público). Ver 'Grupo A', 'Grupo B'."),
    ("fatura", "tipo_fornecimento", "Tipo de ligação: Monofásico, Bifásico ou Trifásico."),
    ("fatura", "tensao_nominal_v", "Tensão nominal disponibilizada pela distribuidora, em volts."),
    ("fatura", "tensao_min_v", "Limite mínimo de tensão admitido, em volts."),
    ("fatura", "tensao_max_v", "Limite máximo de tensão admitido, em volts."),
    ("fatura", "demanda_contratada_kw", "Demanda de potência contratada, em kW. "
               "Vazio quando a fatura não traz o campo de grandezas contratadas; "
               "0 só quando a fatura imprime esse valor explicitamente. "
               "Ver 'Demanda contratada'."),
    ("fatura", "demanda_geracao_contratada_kw", "Demanda de geração contratada, "
               "em kW (Equatorial). Vazio quando a fatura não traz o campo; "
               "0 só quando a fatura imprime esse valor explicitamente."),
    ("fatura", "perdas_transformacao_pct", "Percentual de perdas de transformação/ramal."),
    ("fatura", "scee_geracao_ciclo", "Ciclo de geração do SCEE (formato AAAA_MM), quando a "
               "UC participa do Sistema de Compensação de Energia Elétrica."),
    ("fatura", "scee_saldo_kwh_total", "Saldo total de energia do SCEE em kWh — valor único "
               "após 'SALDO KWH:' ou o valor de 'ATV:' (equivalentes). Vazio quando o saldo "
               "vem só por posto."),
    ("fatura", "scee_saldo_kwh_P", "Saldo do SCEE no posto Ponta (de 'P=' em 'SALDO KWH:')."),
    ("fatura", "scee_saldo_kwh_FP", "Saldo do SCEE no posto Fora Ponta (de 'FP=')."),
    ("fatura", "scee_saldo_kwh_HR", "Saldo do SCEE no posto Reservado/horário (de 'HR=')."),
    ("fatura", "data_leitura_anterior", "Data da leitura anterior do medidor."),
    ("fatura", "data_leitura_atual", "Data da leitura atual do medidor."),
    ("fatura", "numero_dias_leitura", "Número de dias faturados entre as duas leituras."),
    ("fatura", "data_proxima_leitura", "Data prevista para a próxima leitura."),
    # unidade_consumidora
    ("unidade_consumidora", "id_uc", "Código da Unidade Consumidora (UC)."),
    ("unidade_consumidora", "razao_social", "Razão social / nome do titular da UC."),
    ("unidade_consumidora", "cnpj", "CNPJ (ou CPF) do titular."),
    ("unidade_consumidora", "cep", "CEP do endereço da UC."),
    ("unidade_consumidora", "municipio", "Município da UC."),
    ("unidade_consumidora", "uf", "Unidade da Federação (ex.: GO)."),
    # unidade_consumidora — cadastro vindo do dicionário oficial de UCs
    ("unidade_consumidora", "id_uc_dicionario", "UC no formato atual, segundo o dicionário oficial."),
    ("unidade_consumidora", "id_uc_dicionario_sem_format", "Ao lado de id_uc_dicionario: sem ponto ou hífen."),
    ("unidade_consumidora", "id_uc_antigo_dicionario", "UC no formato antigo, segundo o dicionário oficial."),
    ("unidade_consumidora", "id_uc_aneel_bordero", "UC no formato da Resolução ANEEL nº 1095/2024 (borderô), 15 dígitos com zeros à esquerda."),
    ("unidade_consumidora", "uc_operante", "Se a UC está operante segundo o dicionário oficial."),
    ("unidade_consumidora", "medidores_utilizados_dicionario", "Medidores já usados por esta UC ao longo do tempo, segundo o dicionário oficial (vários, separados por '; ', quando a UC trocou de medidor)."),
    ("unidade_consumidora", "medidor_atual_dicionario", "Medidor atualmente em uso nesta UC, segundo o dicionário oficial."),
    ("unidade_consumidora", "unidade_judiciaria", "Unidade judiciária/administrativa atendida por esta UC."),
    ("unidade_consumidora", "uj_uc_at_bt_gd", "Resumo Unidade Judiciária - UC - Grupo (AT/BT) - Geração Distribuída, segundo o dicionário oficial."),
    ("unidade_consumidora", "concessionaria", "Distribuidora responsável pela UC, segundo o dicionário oficial."),
    ("unidade_consumidora", "endereco_dicionario", "Endereço completo da UC, segundo o dicionário oficial (texto livre)."),
    ("unidade_consumidora", "comarca", "Comarca a que pertence a UC, segundo o dicionário oficial."),
    ("unidade_consumidora", "grupo_fornecimento_at_bt", "Grupo de fornecimento (alta ou baixa tensão), segundo o dicionário oficial."),
    ("unidade_consumidora", "limite_fornecimento_tensao", "Faixa de tensão de fornecimento adequada para esta UC, segundo o dicionário oficial."),
    ("unidade_consumidora", "possui_geracao_distribuida", "Se a UC possui geração distribuída (GD), segundo o dicionário oficial."),
    ("unidade_consumidora", "participa_rateio", "Se a UC participa de algum rateio de geração distribuída, segundo o dicionário oficial."),
    ("unidade_consumidora", "e_gerador_rateio", "Se a UC é geradora (não beneficiária) num rateio de geração distribuída."),
    ("unidade_consumidora", "e_beneficiaria_rateio", "Se a UC é beneficiária de créditos de um rateio de geração distribuída."),
    ("unidade_consumidora", "rateio_comum", "Se a UC participa do rateio comum (não vinculado a uma usina específica)."),
    ("unidade_consumidora", "rateio_ufv_cachoeira_dourada", "Se a UC participa do rateio da usina fotovoltaica de Cachoeira Dourada."),
    ("unidade_consumidora", "percentual_rateio", "Percentual de participação da UC no rateio, quando aplicável."),
    ("unidade_consumidora", "demanda_alterada", "Se há um pedido de alteração de demanda contratada em andamento para esta UC, segundo o dicionário oficial."),
    ("unidade_consumidora", "demanda_futura_kw", "Demanda contratada futura (kW), quando há um pedido de alteração em andamento."),
    ("unidade_consumidora", "protocolo_alteracao_demanda", "Número do protocolo do pedido de alteração de demanda contratada, quando aplicável."),
    ("unidade_consumidora", "saldo_scee_cadastro_kwh", "Saldo de créditos do SCEE (kWh), snapshot do dicionário oficial na última atualização (não é o saldo por fatura — ver 'fatura.scee_saldo_kwh_total')."),
    ("unidade_consumidora", "prioridade_rateio", "Ordem de prioridade da UC no rateio de geração distribuída, quando aplicável."),
    ("unidade_consumidora", "gd_sem_rateio", "Se a UC tem geração distribuída própria sem participar de rateio com outras UCs."),
    ("unidade_consumidora", "usina_fotovoltaica_cachoeira_dourada", "Se esta UC É a usina fotovoltaica de Cachoeira Dourada (geradora, não beneficiária)."),
    ("unidade_consumidora", "primeira_competencia", "Competência (AAAA-MM) mais "
               "antiga com fatura para esta UC."),
    ("unidade_consumidora", "ultima_competencia", "Competência (AAAA-MM) mais recente com fatura para esta UC."),
    ("unidade_consumidora", "primeira_fatura", "id_fatura da fatura mais antiga desta UC (pela competência)."),
    ("unidade_consumidora", "ultima_fatura", "id_fatura da fatura mais recente desta UC (pela competência)."),
    ("(todas)", "id_uc", "Aparece em todas as abas; quando a fatura não traz UC, recebe "
               "'NULO_<id_fatura>' (nunca fica vazio)."),
    ("(demais abas)", "id_uc_atual", "Ao lado de id_uc (em todas as abas EXCETO "
               "unidade_consumidora): o id_uc mais recente (por competência) e não-'NULO_' "
               "associado ao mesmo medidor, sem ponto ou hífen. Ajuda a unificar a UC quando "
               "a leitura falhou em alguma fatura."),
    ("unidade_consumidora", "id_uc_sem_format", "Ao lado de id_uc: o mesmo valor, sem ponto ou hífen."),
    ("unidade_consumidora", "id_uc_atual_medidor", "Ao lado de id_uc: o id_uc mais recente (por "
               "competência) e não-'NULO_' associado ao mesmo medidor."),
    ("unidade_consumidora", "id_uc_atual_medidor_sem_format", "Ao lado de id_uc_atual_medidor: "
               "o mesmo valor, sem ponto ou hífen."),
    ("(todas)", "id_uc_canonico", "Aparece em todas as abas com id_uc: a UC segundo o "
               "dicionário oficial (sem ponto ou hífen), que une o histórico da mesma UC "
               "real mesmo quando o formato do id_uc mudou ao longo do tempo ou o medidor "
               "foi trocado. Quando o dicionário não conhece a UC, cai para o id_uc "
               "inferido pelo medidor. É a coluna recomendada para agrupar por UC."),
    # tarifas
    ("tarifas", "fornecedor", "Distribuidora (EQUATORIAL ou CHESP) — parte da chave que identifica cada linha, junto com item e tarifa."),
    ("tarifas", "competencia", "Competência (AAAA-MM) em que esta combinação de fornecedor+item+tarifa apareceu pela primeira vez no acervo."),
    ("tarifas", "item", "Nome do item de fatura (mesmo texto de itens_fatura.item)."),
    ("tarifas", "tarifa_unitaria_r$", "Valor da tarifa sem tributos — parte da chave de deduplicação desta aba."),
    ("(todas exceto unidade_consumidora)", "competencia", "Mês de referência (AAAA-MM) da fatura da linha."),
    ("itens_fatura", "item_normalizado", "Nome padronizado do item conforme a Tabela de "
               "Equivalências (aba Parâmetros); se o item não estiver na tabela, fica igual a 'item'."),
    # itens_fatura
    ("itens_fatura", "id_uc", "Código da Unidade Consumidora da fatura à qual o item pertence."),
    ("itens_fatura", "item", "Nome do item faturado (ver categoria 'Item de fatura')."),
    ("itens_fatura", "tipo", "FORNECIMENTO (energia/demanda) ou ITENS FINANCEIROS (tributos, "
                     "ajustes, créditos, multas, produtos)."),
    ("itens_fatura", "unidade", "Unidade de medida do item (kWh, kW, kVArh, kVar)."),
    ("itens_fatura", "quantidade", "Quantidade medida/faturada do item."),
    ("itens_fatura", "preco_unitario_com_tributos_r$", "Preço unitário com tributos, em R$."),
    ("itens_fatura", "valor_r$", "Valor do item, em reais (negativo = crédito/abatimento)."),
    ("itens_fatura", "pis_cofins", "Parcela de PIS/COFINS do item."),
    ("itens_fatura", "base_calc_icms_r$", "Base de cálculo do ICMS do item, em R$."),
    ("itens_fatura", "aliquota_icms_r$", "Alíquota de ICMS aplicada ao item (%)."),
    ("itens_fatura", "icms", "Valor de ICMS do item, em R$."),
    ("itens_fatura", "tarifa_unitaria_r$", "Tarifa unitária aplicada, em R$."),
    # impostos
    ("impostos", "Tributo", "Tributo: PIS/PASEP, COFINS ou ICMS."),
    ("impostos", "Base (R$)", "Base de cálculo do tributo, em reais."),
    ("impostos", "Aliquota (%)", "Alíquota aplicada (%)."),
    ("impostos", "Valor (R$)", "Valor do tributo, em reais."),
    # medicao
    ("medicao", "Grandezas", "Grandeza medida (ENERGIA ATIVA, DEMANDA, UFER, DMCR, etc.)."),
    ("medicao", "Postos horarios", "Posto horário da medição (PONTA, FORA PONTA, RESERVADO, ÚNICO)."),
    ("medicao", "Leitura Anterior", "Leitura registrada no medidor no início do período."),
    ("medicao", "Leitura Atual", "Leitura registrada no medidor no fim do período."),
    ("medicao", "Const Medidor", "Constante do medidor (fator de multiplicação)."),
    ("medicao", "Consumo kWh", "Consumo apurado no período (Leitura Atual − Anterior × constante)."),
    ("medicao", "Medidor", "Número de série do medidor."),
    # medicao_resumida
    ("medicao_resumida", "energia_geracao_kwh", "Energia gerada (kWh) — é a coluna "
                         "'Consumo kWh' da aba 'medicao' renomeada, filtrada na grandeza "
                         "'ENERGIA GERAÇÃO - KWH'."),
]


# ──────────────────────────────────────────────────────────────────────────────
# 3. Documentação de VALORES / categorias
# ──────────────────────────────────────────────────────────────────────────────
VALORES_DOC = [
    ("EQUATORIAL (fornecedor)", "Faturas da Equatorial Goiás."),
    ("CHESP (fornecedor)", "Faturas da Companhia Hidroelétrica São Patrício (CHESP)."),
    ("FORNECIMENTO (tipo de item)", "Itens de consumo/energia e demanda faturados."),
    ("ITENS FINANCEIROS (tipo de item)", "Tributos retidos, ajustes, créditos, multas, "
        "parcelamentos e produtos cobrados na fatura."),
    ("PONTA (posto horário)", "Três horas diárias consecutivas de maior demanda, definidas "
        "pela distribuidora (exclui fins de semana e feriados)."),
    ("FORA PONTA (posto horário)", "Horas do dia não incluídas no horário de ponta."),
    ("RESERVADO (posto horário)", "Posto horário reservado/intermediário, conforme a tarifa."),
    ("ÚNICO (posto horário)", "Tarifa sem distinção de horário (consumo único)."),
    ("Competência (AAAA-MM)", "Ano e mês de referência do consumo, ex.: 2025-08 = agosto/2025."),
]


# ──────────────────────────────────────────────────────────────────────────────
# 4. CONCEITOS gerais (glossário oficial Equatorial)
# ──────────────────────────────────────────────────────────────────────────────
CONCEITOS = [
    ("Bandeira Tarifária", "Sistema que define acréscimo (ou não) no valor da energia "
        "conforme as condições de geração no país."),
    ("Bandeira verde", "Condições favoráveis de geração, sem acréscimo tarifário."),
    ("Bandeira amarela", "Condições menos favoráveis de geração, com pequeno acréscimo por kWh."),
    ("Bandeira vermelha", "Condições desfavoráveis de geração, com maior acréscimo por kWh "
        "(Patamares 1 e 2)."),
    ("Tarifa de Energia (TE)", "Valor cobrado pela energia efetivamente consumida (kWh)."),
    ("Tarifa de Uso do Sistema de Distribuição (TUSD)", "Custos de manutenção e operação da "
        "infraestrutura de distribuição."),
    ("ICMS", "Imposto estadual sobre Circulação de Mercadorias e Serviços incidente sobre a energia."),
    ("PIS/PASEP", "Programa de Integração Social — tributo federal cobrado na conta."),
    ("COFINS", "Contribuição para o Financiamento da Seguridade Social — tributo federal."),
    ("CIP / Iluminação Pública", "Contribuição municipal para custeio da iluminação pública."),
    ("Encargos setoriais", "Valores criados por lei para implementar políticas públicas do setor elétrico."),
    ("Perdas", "Energia que passa pelas linhas mas não é comercializada, por motivos técnicos/comerciais."),
    ("Demanda", "Média das potências elétricas ativas/reativas durante um intervalo (kW)."),
    ("Demanda contratada", "Potência ativa que a distribuidora disponibiliza obrigatoriamente, "
        "conforme contrato (kW)."),
    ("kWh", "Quilowatt-hora: medida de energia consumida."),
    ("kV", "Quilovolt: múltiplo de volts (1 kV = 1000 V)."),
    ("Grupo A", "Unidades atendidas em alta tensão (≥ 2,3 kV) ou por sistema subterrâneo."),
    ("Grupo B", "Unidades atendidas em baixa tensão (< 2,3 kV)."),
    ("A4", "Subgrupo do Grupo A: tensão de conexão entre 2,3 kV e 25 kV."),
    ("B3", "Subgrupo do Grupo B (baixa tensão), comum a poder público/comércio."),
    ("Monofásico", "Ligação com dois fios (uma fase e um neutro), 127 V ou 220 V."),
    ("Bifásico", "Ligação com três fios (duas fases e um neutro)."),
    ("Trifásico", "Ligação com quatro fios (três fases e um neutro)."),
    ("Unidade Consumidora (UC)", "Conjunto de instalações com medição individualizada em um único ponto de conexão."),
    ("Tarifa", "Valor monetário unitário (R$) definido pela ANEEL para faturamento do consumo."),
    ("Fator de multiplicação / Constante do medidor", "Número pelo qual a leitura é multiplicada "
        "para obter o consumo real."),
    ("DIC", "Duração de Interrupção Individual por unidade consumidora (horas)."),
    ("FIC", "Frequência de Interrupção Individual (número de interrupções por UC)."),
    ("DMIC", "Duração Máxima de Interrupção Contínua por UC (horas)."),
    ("SCEE", "Sistema de Compensação de Energia Elétrica: a energia injetada pela "
        "geração própria (ex.: solar) gera créditos em kWh para abater o consumo."),
    ("Energia injetada", "Energia gerada pela própria UC (ex.: solar) e injetada na rede, gerando créditos."),
    ("UFER", "Energia reativa excedente faturada (consumo de reativo acima do permitido)."),
    ("Origem da leitura", "LIDO (leitura medida) ou NÃO LIDO/ESTIMADA (quando não foi possível medir)."),
    ("Comarca", "Circunscrição judiciária que engloba um ou mais municípios, para fins de "
        "organização do Poder Judiciário."),
    ("Unidade Judiciária (UJ)", "Órgão/unidade do Poder Judiciário atendido por uma Unidade "
        "Consumidora de energia."),
    ("Rateio", "Divisão dos créditos de energia gerados por uma usina de geração distribuída "
        "entre várias UCs beneficiárias, conforme percentual definido."),
    ("Resolução ANEEL nº 1095/2024", "Resolução que define o formato de agrupamento de UCs em "
        "borderôs de pagamento — usada como um dos identificadores oficiais da UC no dicionário."),
]


# ──────────────────────────────────────────────────────────────────────────────
# Construção da aba
# ──────────────────────────────────────────────────────────────────────────────
def _carregar_itens() -> list[dict]:
    fp = _RES / "glossario_itens.json"
    try:
        return json.loads(fp.read_text(encoding="utf-8"))
    except Exception:
        return []


def construir_glossario_df() -> pd.DataFrame:
    rows: list[tuple[str, str, str]] = []  # (Termo, Categoria, Definição)
    for termo, defin in ABAS_DOC:
        rows.append((termo, "Aba da planilha", defin))
    for aba, col, defin in COLUNAS_DOC:
        rows.append((col, f"Coluna · {aba}", defin))
    for termo, defin in VALORES_DOC:
        rows.append((termo, "Valor / categoria", defin))
    for termo, defin in CONCEITOS:
        rows.append((termo, "Conceito geral", defin))
    for it in _carregar_itens():
        rows.append((it["termo"], "Item de fatura", it["definicao"]))
    return pd.DataFrame(rows, columns=["Termo", "Categoria", "Definição"])


def _norm(nome: str) -> str:
    s = unicodedata.normalize("NFKD", str(nome)).encode("ascii", "ignore").decode()
    return s.strip().lower()


def garantir_glossario(display_dfs: dict) -> dict:
    """
    Garante a presença da aba de glossário no conjunto de abas de saída.
    Se já existir uma aba 'glossario'/'glossário' (ex.: na planilha enviada),
    NÃO a substitui (preserva a do usuário).
    """
    if any(_norm(k) == "glossario" for k in display_dfs):
        return display_dfs
    novo = dict(display_dfs)
    novo[NOME_ABA] = construir_glossario_df()
    return novo
