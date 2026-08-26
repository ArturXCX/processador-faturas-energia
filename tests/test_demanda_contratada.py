"""
Testes de `demanda_contratada_kw` / `demanda_geracao_contratada_kw`, com
trechos REAIS de texto de fatura (sem depender dos PDFs em disco).

Cobrem duas mudanças que andam juntas no mesmo bloco de código:

  - **Nulo, não zero**: quando a fatura não traz o campo de grandezas
    contratadas, a célula fica VAZIA. Antes gravava `0`, o que misturava
    "a fatura não tem esse campo" com "a fatura diz 0" — e 0 é um valor que a
    fatura pode imprimir de verdade.
  - **CHESP "Modelo 6"** (nota antiga P&B, jan–mai/2022): a demanda contratada
    é impressa no cabeçalho ("DEMANDA CONTR.: 60"), fora do bloco "GRANDEZAS
    CONTRATADAS" do layout colorido — o valor era perdido.

Os testes de layout que JÁ funcionavam (colorido/Equatorial) são os mais
importantes daqui: são eles que travam a não regressão.

Rodar:  PYTHONPATH=src python -m pytest tests/ -q
   ou:  PYTHONPATH=src python tests/test_demanda_contratada.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from faturas_app.core import chesp, equatorial  # noqa: E402


# ── CHESP ────────────────────────────────────────────────────────────────────
def test_chesp_modelo6_demanda_contr():
    """FATURA_N_38841.pdf (UC 31811020, Modelo 6, fev/2022): 'DEMANDA CONTR.: 60'."""
    txt = "FATOR DE POT.: 99,91\nDEMANDA CONTR.: 60\nDATAS\n"
    fat = chesp.extrair_fatura_chesp(txt, "38841.pdf")
    assert fat["demanda_contratada_kw"] == 60.0


def test_chesp_modelo6_nao_confunde_com_item_demanda():
    """
    O rótulo do cabeçalho ('DEMANDA CONTR.:') não pode ser confundido com a
    LINHA DE ITEM 'DEMANDA 60 18,92000 1.135,20', que aparece mais adiante na
    mesma fatura e não tem a palavra 'CONTR'. Aqui só o item existe: sem
    rótulo de contratada, o campo fica nulo.
    """
    txt = "ITENS DE FATURA\nDEMANDA 45 18,92000 851,40\n"
    fat = chesp.extrair_fatura_chesp(txt, "x.pdf")
    assert fat["demanda_contratada_kw"] is None


def test_chesp_sem_grandezas_contratadas_fica_nulo():
    """Fatura sem nenhum dos três rótulos: nulo, não zero."""
    txt = "TOTAL A PAGAR R$100,00\n"
    fat = chesp.extrair_fatura_chesp(txt, "x.pdf")
    assert fat["demanda_contratada_kw"] is None


def test_chesp_colorido_continua_igual():
    """Regressão: layout colorido (GRANDEZAS CONTRATADAS) não pode mudar."""
    txt = "GRANDEZAS CONTRATADAS\nDemanda fora ponta-kW 100\n"
    fat = chesp.extrair_fatura_chesp(txt, "x.pdf")
    assert fat["demanda_contratada_kw"] == 100.0


def test_chesp_demanda_kw_inicio_de_linha_continua_igual():
    """Regressão: 2º rótulo já existente ('^DEMANDA kW 45') não pode mudar."""
    txt = "GRANDEZAS CONTRATADAS\nDEMANDA kW 45\n"
    fat = chesp.extrair_fatura_chesp(txt, "x.pdf")
    assert fat["demanda_contratada_kw"] == 45.0


def test_chesp_zero_impresso_continua_zero():
    """Zero REALMENTE impresso na fatura continua 0 — o nulo é só para ausência."""
    txt = "GRANDEZAS CONTRATADAS\nDemanda fora ponta-kW 0\n"
    fat = chesp.extrair_fatura_chesp(txt, "x.pdf")
    assert fat["demanda_contratada_kw"] == 0.0


# ── EQUATORIAL ───────────────────────────────────────────────────────────────
def test_equatorial_sem_grandezas_contratadas_fica_nulo():
    txt = "CLASSIFICAÇÃO: B B3 CONVENCIONAL MONOFÁSICO\n"
    fat = equatorial.extrair_fatura(txt, "x.pdf", numero_forcado="1")
    assert fat["demanda_contratada_kw"] is None
    assert fat["demanda_geracao_contratada_kw"] is None


def test_equatorial_com_grandezas_contratadas_continua_igual():
    """Regressão: o layout que já capturava não pode mudar."""
    txt = "DEMANDA - kW 60\n"
    fat = equatorial.extrair_fatura(txt, "x.pdf", numero_forcado="1")
    assert fat["demanda_contratada_kw"] == 60.0


def test_equatorial_demanda_geracao_continua_igual():
    """A demanda de GERAÇÃO tem rótulo próprio e é lida em separado."""
    txt = "DEMANDA - kW 60\nDEMANDA GERAÇÃO - kW 75\n"
    fat = equatorial.extrair_fatura(txt, "x.pdf", numero_forcado="1")
    assert fat["demanda_contratada_kw"] == 60.0
    assert fat["demanda_geracao_contratada_kw"] == 75.0


def test_equatorial_so_demanda_geracao_deixa_a_outra_nula():
    """Uma presente e a outra ausente: só a ausente fica nula."""
    txt = "DEMANDA GERAÇÃO - kW 75\n"
    fat = equatorial.extrair_fatura(txt, "x.pdf", numero_forcado="1")
    assert fat["demanda_geracao_contratada_kw"] == 75.0
    assert fat["demanda_contratada_kw"] is None


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
