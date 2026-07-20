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
    ("cliente", "Dados cadastrais da Unidade Consumidora (razão social, CNPJ, "
                "endereço). Uma linha por UC."),
    ("itens_fatura", "Itens que compõem a fatura (energia, demanda, tributos, "
                     "ajustes). Várias linhas por fatura; ver categoria 'Item de fatura'."),
    ("impostos", "Tributos incidentes (PIS/PASEP, COFINS, ICMS) com base de "
                 "cálculo, alíquota e valor."),
    ("medicao", "Grandezas medidas (energia ativa, demanda, etc.) por posto "
                "horário, com leituras e consumo."),
    ("fatura_resumida", "Versão enxuta da aba 'fatura' (primeira aba): apenas "
                        "identificação, classificação, demandas, SCEE e dias de leitura."),
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
    ("fatura", "demanda_contratada_kw", "Demanda de potência contratada, em kW (0 quando "
               "não há contrato de demanda). Ver 'Demanda contratada'."),
    ("fatura", "demanda_geracao_contratada_kw", "Demanda de geração contratada, em kW "
               "(Equatorial; 0 quando ausente)."),
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
    # cliente
    ("cliente", "id_uc", "Código da Unidade Consumidora (UC)."),
    ("cliente", "razao_social", "Razão social / nome do titular da UC."),
    ("cliente", "cnpj", "CNPJ (ou CPF) do titular."),
    ("cliente", "cep", "CEP do endereço da UC."),
    ("cliente", "municipio", "Município da UC."),
    ("cliente", "uf", "Unidade da Federação (ex.: GO)."),
    ("cliente", "ultima_competencia", "Competência (AAAA-MM) mais recente com fatura para esta UC."),
    ("cliente", "ultima_fatura", "id_fatura da fatura mais recente desta UC (pela competência)."),
    ("(todas)", "id_uc", "Aparece em todas as abas; quando a fatura não traz UC, recebe "
               "'NULO_<id_fatura>' (nunca fica vazio)."),
    ("(todas)", "id_uc_normalizado", "Ao lado de id_uc: o id_uc mais recente (por competência) "
               "e não-'NULO_' associado ao mesmo medidor. Ajuda a unificar a UC quando a "
               "leitura falhou em alguma fatura."),
    ("(todas exceto cliente)", "competencia", "Mês de referência (AAAA-MM) da fatura da linha."),
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
