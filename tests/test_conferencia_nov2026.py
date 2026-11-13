"""Correções de nov/2026, vindas da conferência das quatro organizações do gEEstor (trechos REAIS de texto de fatura).

  - Tarifa AZUL: a caixa de grandezas contratadas traz "DEMANDA NA PONTA - kW" e "DEMANDA FORA DE PONTA - kW" (não o
    "DEMANDA - kW" da verde); mercado livre traz "DEMANDA LIVRE - kW".
  - Nome de item financeiro quebrado em duas linhas, com a 1ª caindo na linha do histórico de consumo.
  - Fatura cuja única linha de medição não tem leitura nenhuma (só constante e consumo).
  - Soma dos itens que não fecha porque o PDF repete, fora da área visível da 1ª página, o conteúdo da página de continuação.

Todas só entram onde o resultado anterior estava errado: os testes "não muda" travam a não regressão."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from faturas_app.core import equatorial as E  # noqa: E402
from faturas_app.core import schema  # noqa: E402


# ── demanda contratada ───────────────────────────────────────────────────────
def test_azul_ponta_e_fora_de_ponta():
    """EQUATORIAL_2024039449493 (DGPP, THS_AZUL): 570 / 570; UFG (10013360033): 400 na ponta, 550 fora."""
    txt = "Classificação: A A4 PODER PÚBLICO - FEDERAL THS_AZUL\nDEMANDA NA PONTA - kW 400\nDEMANDA FORA DE PONTA - kW 550\n03/05/2024\n"
    fat = E.extrair_fatura(txt, "2024039449493.pdf")
    assert fat["demanda_contratada_kw"] == 550.0
    assert fat["demanda_contratada_ponta_kw"] == 400.0


def test_azul_rotulo_e_valor_em_linhas_separadas():
    txt = "DEMANDA NA PONTA - kW\n60\nDEMANDA FORA DE PONTA - kW\n100\nCNPJ/CPF:\n"
    fat = E.extrair_fatura(txt, "x.pdf")
    assert (fat["demanda_contratada_kw"], fat["demanda_contratada_ponta_kw"]) == (100.0, 60.0)


def test_verde_nao_muda_e_nao_ganha_a_chave_da_ponta():
    """Fatura com o rótulo convencional: mesmo valor de antes e nenhuma chave nova no resultado."""
    txt = "10518201-0 DEMANDA - KW PONTA 051610 052118 0,120000 62,484\nDEMANDA kW 92,62 32,987740 3.055,29\nDEMANDA - kW 84\nPIS/PASEP 8408,39 0,7093% 59,64\n"
    fat = E.extrair_fatura(txt, "x.pdf")
    assert fat["demanda_contratada_kw"] == 84.0
    assert "demanda_contratada_ponta_kw" not in fat


def test_rotulo_convencional_tem_prioridade_sobre_os_da_azul():
    txt = "DEMANDA - kW 84\nDEMANDA NA PONTA - kW 60\nDEMANDA FORA DE PONTA - kW 100\n"
    fat = E.extrair_fatura(txt, "x.pdf")
    assert fat["demanda_contratada_kw"] == 84.0 and "demanda_contratada_ponta_kw" not in fat


def test_linhas_da_medicao_e_dos_itens_nao_sao_demanda_contratada():
    """'DEMANDA - KW PONTA 002647 …' (medição) e 'DEMANDA P - kW kW 30,00 …' (item) não têm o rótulo da caixa."""
    txt = ("12358712-3 DEMANDA - KW PONTA 002647 002718 1,440000 102,24\n12358712-3 DEMANDA - KW FORA PONTA 009979 010313 1,440000 480,96\n"
           "DEMANDA P - kW kW 30,00 32,356400 970,69 14,48 970,69 29% 281,5 22,49\n")
    fat = E.extrair_fatura(txt, "x.pdf")
    assert fat["demanda_contratada_kw"] is None and "demanda_contratada_ponta_kw" not in fat


def test_mercado_livre_demanda_livre():
    """Fatura de consumidor livre (UFG/2022): 'DEMANDA LIVRE - kW 700'."""
    fat = E.extrair_fatura("TOTAL 23.351,11 1.016,59 23.281,69 0,00\nDEMANDA LIVRE - kW 700 Diferimento conforme Art. 30\n", "x.pdf")
    assert fat["demanda_contratada_kw"] == 700.0 and "demanda_contratada_ponta_kw" not in fat


def test_sem_contrato_continua_zero_e_sem_caixa_continua_nulo():
    assert E.extrair_fatura("CONSUMO S/ CONTRATO kWh 100,00 0,5 50,00\n", "x.pdf")["demanda_contratada_kw"] == 0.0
    assert E.extrair_fatura("CONSUMO kWh 100,00 0,5 50,00\n", "x.pdf")["demanda_contratada_kw"] is None


def test_coluna_da_ponta_no_schema_e_nao_protegida():
    """Fica ao lado da demanda contratada e some da planilha quando o lote não tem fatura azul (coluna 100% vazia)."""
    for aba in ("fatura", "fatura_resumida"):
        cols = schema.CANONICAL_COLUMNS[aba]
        assert cols.index("demanda_contratada_ponta_kw") == cols.index("demanda_contratada_kw") + 1
    assert "demanda_contratada_ponta_kw" not in schema.COLS_PROTEGIDAS


# ── nome do item quebrado na linha do histórico ──────────────────────────────
TEXTO_QUEBRADO = ("ITENS FINANCEIROS\nTIPOS DE\nCRÉDITO DE CONSUMO - 06/2026 -129,05 MÊS/ANO CONSUMO FATURADO(kWh) DIAS FATURAMENTO\n"
                  "IR LEI 9430(-) -1,60 4332,59\nJUROS DEV. FAT. A MAIOR - CRÉDITO DE CONSUMO - 4563,00 29 LIDA\n06/2026 -2,34\n3690,00 30 LIDA\n"
                  "TOTAL 0,00 5,19 132,99 0,00\n")


def _it(nome, v, tipo="ITENS FINANCEIROS"):
    return {"id_fatura": "X", "item": nome, "tipo": tipo, "valor_r$": v}


def test_nome_quebrado_troca_o_consumo_do_historico_pelo_valor_do_item():
    """EQUATORIAL_2026089862783 (TJGO): o 4563,00 é o consumo do histórico; o item vale -2,34 e o total é 0,00."""
    itens = [_it("CONSUMO", 132.99, "FORNECIMENTO"), _it("CRÉDITO DE CONSUMO - 06/2026", -129.05), _it("IR LEI 9430(-)", -1.60),
             _it("JUROS DEV. FAT. A MAIOR - CRÉDITO DE CONSUMO", 4563.0)]
    r = E._completar_itens(itens, TEXTO_QUEBRADO, 0.0, "X")
    assert [(i["item"], i["valor_r$"]) for i in r][-1] == ("JUROS DEV. FAT. A MAIOR - CRÉDITO DE CONSUMO - 06/2026", -2.34)
    assert abs(sum(i["valor_r$"] for i in r)) < 0.01
    assert itens[-1]["valor_r$"] == 4563.0, "a lista original não é alterada"


def test_nome_quebrado_so_troca_se_a_soma_fechar():
    itens = [_it("CONSUMO", 132.99, "FORNECIMENTO"), _it("JUROS DEV. FAT. A MAIOR - CRÉDITO DE CONSUMO", 4563.0)]
    texto = "JUROS DEV. FAT. A MAIOR - CRÉDITO DE CONSUMO - 4563,00 29 LIDA\n06/2026 -2,34\n"
    assert E._completar_itens(itens, texto, 999.0, "X") == itens


def test_fatura_que_fecha_nao_muda_mesmo_com_o_padrao_no_texto():
    itens = [_it("CONSUMO", 4563.0, "FORNECIMENTO")]
    assert E._completar_itens(itens, TEXTO_QUEBRADO, 4563.0, "X") is itens


# ── medição sem leitura nenhuma ──────────────────────────────────────────────
def test_unica_linha_de_medicao_sem_leituras():
    """EQUATORIAL_2024090173902 (UFG): '1709562-0 ENERGIA ATIVA - KWH ÚNICO 0,180000 174' (faturamento sem leitura)."""
    med = E.extrair_medicao("Medidor Grandezas Postos horários\n1709562-0 ENERGIA ATIVA - KWH ÚNICO 0,180000 174\nReservado ao Fisco\n", "X")
    assert len(med) == 1
    assert (med[0]["Medidor"], med[0]["Const Medidor"], med[0]["Consumo kWh"]) == ("1709562-0", 0.18, 174.0)
    assert (med[0]["Leitura Anterior"], med[0]["Leitura Atual"]) == (0, 0)


def test_linha_sem_leituras_nao_entra_quando_a_fatura_ja_tem_medicao():
    """Só vale para a fatura que ficaria sem medição: quem já tem linhas não ganha linha nova."""
    txt = ("2993839-2 ENERGIA ATIVA - KWH ÚNICO 763377 763500 1,000000 123\n"
           "2993839-2 ENERGIA REATIVA - KWH ÚNICO 0,180000 174\n")
    med = E.extrair_medicao(txt, "X")
    assert [m["Grandezas"] for m in med] == ["ENERGIA ATIVA - KWH"]


# ── releitura só da área visível ─────────────────────────────────────────────
def test_soma_nao_fecha_ignora_demonstrativos_e_tolera_um_real():
    r = {"fatura": {"valor_total_r$": 100.0},
         "itens_fatura": [{"item": "CONSUMO", "valor_r$": 100.5}, {"item": "UFER DEMONSTRATIVO HORÁRIO RESERVADO", "valor_r$": 4.28}]}
    assert not E._soma_nao_fecha(r)
    r["itens_fatura"].append({"item": "VALOR CORREÇÃO IPCA.", "valor_r$": 117.06})
    assert E._soma_nao_fecha(r)
    assert not E._soma_nao_fecha({"fatura": {"valor_total_r$": None}, "itens_fatura": []})


def test_reforco_nao_rele_fatura_que_fecha(monkeypatch):
    """A releitura da área visível só acontece quando a soma não fecha; fatura certa nem abre o PDF de novo."""
    certo = {"fatura": {"id_fatura": "EQUATORIAL_1", "valor_total_r$": 10.0}, "itens_fatura": [{"item": "CONSUMO", "valor_r$": 10.0}]}
    monkeypatch.setattr(E, "_montar_resultado", lambda txt, pdf, numero_forcado=None, usou_ocr=False: certo)
    monkeypatch.setattr(E, "extrair_texto_visivel", lambda pdf: (_ for _ in ()).throw(AssertionError("não devia reler")))
    assert E._montar_com_reforco("txt", "x.pdf", False) is certo


def test_reforco_so_aceita_a_releitura_que_fecha(monkeypatch):
    dobro = {"fatura": {"id_fatura": "EQUATORIAL_1", "valor_total_r$": 100.0},
             "itens_fatura": [{"item": "CONSUMO", "valor_r$": 100.0}, {"item": "VALOR CORREÇÃO IPCA.", "valor_r$": 17.0}, {"item": "VALOR CORREÇÃO IPCA.", "valor_r$": 17.0}]}
    certo = {"fatura": {"id_fatura": "EQUATORIAL_1", "valor_total_r$": 100.0},
             "itens_fatura": [{"item": "CONSUMO", "valor_r$": 83.0}, {"item": "VALOR CORREÇÃO IPCA.", "valor_r$": 17.0}]}
    ainda_errado = {"fatura": {"id_fatura": "EQUATORIAL_1", "valor_total_r$": 100.0}, "itens_fatura": [{"item": "CONSUMO", "valor_r$": 60.0}]}
    monkeypatch.setattr(E, "extrair_texto_visivel", lambda pdf: "visivel")
    monkeypatch.setattr(E, "_montar_resultado", lambda txt, pdf, numero_forcado=None, usou_ocr=False: certo if txt == "visivel" else dobro)
    assert E._montar_com_reforco("inteiro", "x.pdf", False) is certo
    monkeypatch.setattr(E, "_montar_resultado", lambda txt, pdf, numero_forcado=None, usou_ocr=False: ainda_errado if txt == "visivel" else dobro)
    assert E._montar_com_reforco("inteiro", "x.pdf", False) is dobro
    monkeypatch.setattr(E, "extrair_texto_visivel", lambda pdf: None)       # PDF sem texto fora da página: nada a reler
    assert E._montar_com_reforco("inteiro", "x.pdf", False) is dobro
