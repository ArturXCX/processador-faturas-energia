"""Equatorial: itens financeiros fora do lugar, recuperados só quando a soma dos itens não fecha com o total (faturas da UFG, 2023–2026)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from faturas_app.core import equatorial as E  # noqa: E402


def _it(nome, v, tipo="FORNECIMENTO"):
    return {"id_fatura": "X", "item": nome, "tipo": tipo, "valor_r$": v}


def test_fatura_que_fecha_nao_muda():
    itens = [_it("CONSUMO", 100.0)]
    assert E._completar_itens(itens, "MULTA - 08/2024. 50,00\nIR LEI 9430(-) -1,00", 100.0, "X") is itens


def test_retencoes_do_layout_antigo_na_linha_da_medicao():
    texto = ("12358805-7 DEMANDA - KW PONTA 012695 012937 0,028800 7,1438 CSLL (1,0%)LEI 9430(-) -30,84\n"
             "COFINS (3,0%) LEI 9430(-) -92,52\n12358805-7 DEMANDA - KW RESERVADO 009032 009185 0,028800 4,5165 IR (1,2%)LEI 9430(-) -37,00\n"
             "PIS/PASEP (0,65 %)LEI 9430(-) -20,04")
    r = E._completar_itens([_it("CONSUMO", 3095.68)], texto, 2915.28, "X")
    assert {i["item"]: i["valor_r$"] for i in r[1:]} == {"CSLL LEI 9430(-)": -30.84, "COFINS LEI 9430(-)": -92.52, "IR LEI 9430(-)": -37.0, "PIS/PASEP LEI 9430(-)": -20.04}
    assert all(i["tipo"] == "ITENS FINANCEIROS" for i in r[1:])
    assert abs(sum(i["valor_r$"] for i in r) - 2915.28) < 0.01


def test_itens_da_segunda_pagina_ao_lado_dos_impostos():
    texto = "MULTA - 04/2026. 678,13 ICMS 36395,36 19% 6915,12\nICMS ENERGIA INJET RET 1/26 24,05\nPAGAMENTO A MAIOR. -13,00\nVALOR CORREÇÃO IPCA. 52,45"
    r = E._completar_itens([_it("CONSUMO", 1000.0)], texto, 1741.63, "X")
    assert {i["item"] for i in r[1:]} == {"MULTA - 04/2026.", "ICMS ENERGIA INJET RET 1/26", "PAGAMENTO A MAIOR.", "VALOR CORREÇÃO IPCA."}


def test_item_ja_lido_nao_duplica_nem_com_nome_grudado():
    itens = [_it("CONSUMO", 100.0), _it("FATOR DE POTÊNCIA ÚNICO MULTA - 01/2023.", 609.77, "ITENS FINANCEIROS")]
    r = E._completar_itens(itens, "MULTA - 01/2023. 609,77\nJUROS MORATÓRIA. 5,00", 714.77, "X")
    assert [i["item"] for i in r] == ["CONSUMO", "FATOR DE POTÊNCIA ÚNICO MULTA - 01/2023.", "JUROS MORATÓRIA."]


def test_nao_acrescenta_o_que_afasta_do_total():
    itens = [_it("CONSUMO", 100.0)]
    assert E._completar_itens(itens, "MULTA - 01/2023. 500,00", 90.0, "X") is itens


def test_fim_de_nome_na_linha_do_historico_nao_e_item():
    itens = [_it("CONSUMO", 74.84), _it("CRÉDITO", -74.84, "ITENS FINANCEIROS"), _it("CONSUMO - 09/2022", 102.08, "ITENS FINANCEIROS")]
    r = E._completar_itens(itens, "", 0.0, "X")
    assert [i["item"] for i in r] == ["CONSUMO", "CRÉDITO"]


def test_fim_de_nome_e_retencoes_na_mesma_fatura():
    itens = [_it("CONSUMO", 74.84), _it("CRÉDITO", -70.0, "ITENS FINANCEIROS"), _it("CONSUMO - 09/2022", 102.08, "ITENS FINANCEIROS")]
    r = E._completar_itens(itens, "COFINS (3,0%) LEI 9430(-) -4,84", 0.0, "X")
    assert [i["item"] for i in r] == ["CONSUMO", "CRÉDITO", "COFINS LEI 9430(-)"]


def test_injecao_com_marca_de_rodape_no_nome():
    texto = ("FORNECIMENTO\nINJEÇÃO SCEE FP - TE - GD II 1 kWh 93204 0,022435 -2.091,03 -38,74 0,022020\nITENS FINANCEIROS\nTOTAL 1,00")
    itens = E.extrair_itens_fatura(texto, "X")
    assert [(i["item"], i["valor_r$"]) for i in itens] == [("INJEÇÃO SCEE FP - TE - GD II", -2091.03)]


def test_servico_com_quantidade_nao_usa_a_quantidade_como_valor():
    texto = "FORNECIMENTO\nCONSUMO kWh 10 1,000000 10,00 0,10 10,00 19% 1,90 0,8\nITENS FINANCEIROS\nTAXA VISTORIA UNID. CONSUMIDORA 1,00 27,020000 27,02\nTOTAL 37,02"
    assert ("TAXA VISTORIA UNID. CONSUMIDORA", 27.02) in [(i["item"], i["valor_r$"]) for i in E.extrair_itens_fatura(texto, "X")]
