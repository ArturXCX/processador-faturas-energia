"""Leitor das faturas antigas da ENEL (core/enel.py): números do OCR, itens e reconciliação.
As linhas são do OCR real de faturas do INMETRO (2018–2021); nada aqui roda o Tesseract."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from faturas_app.core import enel  # noqa: E402


def test_candidatos_valor_ruido_do_ocr():
    assert enel.candidatos_valor("— ****2.040,88")[0] == 2040.88
    assert enel.candidatos_valor("— *****-180,69.")[0] == -180.69
    assert enel.candidatos_valor("t1224")[0] == 12.24             # vírgula perdida
    assert enel.candidatos_valor("607 09")[0] == 607.09           # vírgula lida como espaço
    assert enel.candidatos_valor("2 315,92")[0] == 2315.92        # milhar com espaço
    assert 1861.78 in enel.candidatos_valor("****1.861,788")      # dígito a mais nos centavos
    assert 126.28 in enel.candidatos_valor("rer11126,28")         # asteriscos lidos como dígitos
    assert enel.candidatos_valor("aA") == []


def test_tarifa_sem_virgula():
    assert enel._tarifa("0,061210") == 0.06121
    assert enel._tarifa("2437360") == 2.43736                     # '2,437360' sem a vírgula
    assert enel._tarifa("0,06/210") == 0.06121                    # '1' lido como '/'


def test_itens_duas_colunas_ancorados_na_tarifa():
    linha = ("COFINS (3,0%) LEI 9430 (-) 0,000000 — *****-24282 "
             "CONSUMO FP - kWh 9362,35 0,122560 — ***1.147,44")
    a, b = enel._itens_da_linha(linha)
    assert enel.canonico(a["nome"])[0] == "COFINS LEI 9430(-)"
    assert a["tarifa"] == 0.0
    assert enel.canonico(b["nome"])[0] == "CONSUMO FP"
    assert b["qtd"] == 9362.35 and b["tarifa"] == 0.12256 and b["cands"][0] == 1147.44


def test_canonico():
    assert enel.canonico("PIS/PASEP (0,65 %)LE! 9430 (-)")[0] == "PIS/PASEP LEI 9430(-)"
    assert enel.canonico("IMP.DE RENDA (1,2%)LEI! 9430(-)")[0] == "IR LEI 9430(-)"
    assert enel.canonico("pARCELATEHR")[0] == "PARCELA TE HR"
    assert enel.canonico("ADC BAND. AMARELA HR")[0] == "ADC BAND. AMARELA HR"
    assert enel.canonico("AD. BAND. VERMELHA PARCELA TE P - kWh")[0] == "ADC BAND. VERMELHA TE P"
    assert enel.canonico("CONSUMO KWH + ICMS/PIS/COFINS")[0] == "CONSUMO"
    assert enel.canonico("YFERP")[0] == "UFER P"


def test_sinal_das_retencoes_e_creditos():
    assert enel._sinal("COFINS LEI 9430(-)", "ITENS FINANCEIROS", 12.24, 0.0) == -12.24
    assert enel._sinal("COMPENSAÇÃO DE FIC MENSAL", "ITENS FINANCEIROS", 57.53, 0.0) == -57.53
    assert enel._sinal("CONTRIB. ILUM. PÚBLICA - MUNICIPAL", "ITENS FINANCEIROS", -15.2, 0.0) == 15.2


def _grupo(nome, leituras, qtd=None, tarifa=None):
    nome_c, tipo, unid = enel.canonico(nome)
    return {"nome": nome_c, "tipo": tipo, "unidade": unid, "col": 0, "y": 0,
            "leituras": dict(enumerate(leituras)), "qtds": [qtd] * len(leituras) if qtd else [],
            "tarifas": [tarifa] * len(leituras) if tarifa is not None else []}


def test_reconciliacao_escolhe_a_leitura_que_fecha_com_o_total():
    # fatura 03/2019 (Goiânia): o OCR leu '4,29315' (= 4.293,15) e perdeu o '-' do IR
    grupos = [
        _grupo("UFER FP", [[0.94]], 2.05, 0.4602),
        _grupo("UFER P", [[0.15]], 0.34, 0.46021),
        _grupo("PIS/PASEP (0,65 %)LEI 9430 (-)", [[-49.55]], tarifa=0.0),
        _grupo("IMP.DE RENDA (1,2%)LEI! 9430(-)", [[91.47]], tarifa=0.0),
        _grupo("DEMANDA", [[2040.88]], 75, 27.21184),
        _grupo("CONTRIB. ILUMINAÇÃO PÚBLICA - MUNICIPAL", [[15.2]], tarifa=0.0),
        _grupo("CONTR.SOC.S/LUCRO LIQ.(1,0%) LEI 9430(-)", [[-76.23]], tarifa=0.0),
        _grupo("CONSUMO P", [enel.candidatos_valor("*B42 91")], 337.61, 2.49672),
        _grupo("CONSUMO HR", [[445.22]], 797.45, 0.55831),
        _grupo("CONSUMO FP", [enel.candidatos_valor("***4,29315")], 7689.55, 0.55831),
        _grupo("COFINS LEI 9430(-)", [[-228.69]], tarifa=0.0),
    ]
    tot, desvio = enel._reconciliar(grupos, 1, [(719251, 3)], [(762325, 4)])
    assert tot == 719251 and desvio == 0
    valores = {g["nome"]: g["valor"] for g in grupos}
    assert valores["IR LEI 9430(-)"] == -9147
    assert valores["CONSUMO FP"] == 429315
    assert valores["CONSUMO P"] == 84291                     # quantidade × tarifa, truncado


def test_reconciliacao_recusa_total_que_e_lixo():
    grupos = [_grupo("CONSUMO KWH + ICMS/PIS/COFINS", [[435.0], [435.0]], 528, 0.82388),
              _grupo("CONTRIB. ILUMINAÇÃO PÚBLICA - MUNICIPAL", [[11.36], [11.36]], tarifa=0.0)]
    tot, _ = enel._reconciliar(grupos, 2, [(756, 3)], [])           # '7,56' lido no lugar do total
    assert tot is None


def test_layouts():
    assert enel.layout("NOTA FISCAL/FATURA DE ENERGIA ELÉTRICA\nITENS QTD VALOR UNIT. VALOR") == "B_2020"
    assert enel.layout("FATURA DO SERVIÇO DE FORNECIMENTO DE ENERGIA ELÉTRICA - GRUPO A\nLANÇAMENTOS") == "GRUPO_A"
    assert enel.layout("LANÇAMENTOS\nFATURAMENTO / FORNECIMENTO QUANTIDADE TARIFA VALOR") == "B_2018"
    assert enel.layout("DANEM - DOCUMENTO AIOLIAR DA NOTA FISCAL DE ENERGIA") == "DANF3E"
    assert enel.layout("texto qualquer") is None
