"""Tabelas digitalizadas da Saneago: o modelo de OCR `por_fast` só entra se a leitura não piorar."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from faturas_app.core.agua import extrator  # noqa: E402
from faturas_app.core.agua.base import Resultado  # noqa: E402


class _Doc:
    usou_ocr = True
    criados = []

    def __init__(self, caminho, ocr=True, dpi=300, lang="por"):
        self.lang, self.dpi = lang, dpi
        _Doc.criados.append((lang, dpi))


def _bordero(bate, agua_conta, agua_rodape=100.0):
    r = Resultado()
    r.borderos = [{"id_bordero_agua": "B1", "fornecedor": "SANEAGO", "bate_total": bate, "valor_agua": agua_rodape, "consumo_total_m3": None}]
    r.contas_bordero = [{"id_bordero_agua": "B1", "conta": "1", "valor_agua": agua_conta, "consumo_m3": None, "valor_total": agua_conta}]
    r.consumo_rodape_lido = {"B1": None}
    return r


def _preparar(monkeypatch, por_lang, idioma="por_fast"):
    _Doc.criados = []
    monkeypatch.setattr(extrator, "Documento", _Doc)
    monkeypatch.setattr(extrator, "processar_documento", lambda doc, caminho, fornecedor=None: por_lang[doc.lang])
    monkeypatch.setattr(extrator.ocr_motor, "idioma_tabelas", lambda: idioma)


def test_fica_com_o_fast_quando_ele_fecha(monkeypatch):
    base, fast = _bordero("NÃO", 90.0), _bordero("SIM", 100.0)
    _preparar(monkeypatch, {"por": base, "por_fast": fast})
    assert extrator.processar_pdf("x.pdf") is fast
    assert _Doc.criados == [("por", 300), ("por_fast", 300)]


def test_mantem_o_padrao_quando_o_fast_piora(monkeypatch):
    base, fast = _bordero("SIM", 100.0), _bordero("NÃO", 50.0)
    _preparar(monkeypatch, {"por": base, "por_fast": fast})
    assert extrator.processar_pdf("x.pdf") is base


def test_releitura_usa_o_modelo_escolhido(monkeypatch):
    fast = _bordero("SIM", 90.0)          # o total fecha, mas a coluna de água não: relê com o mesmo modelo
    _preparar(monkeypatch, {"por": _bordero("NÃO", 80.0), "por_fast": fast})
    extrator.processar_pdf("x.pdf")
    assert ("por_fast", 400) in _Doc.criados and ("por", 400) not in _Doc.criados


def test_sem_o_modelo_nao_muda_nada(monkeypatch):
    base = _bordero("SIM", 100.0)
    _preparar(monkeypatch, {"por": base}, idioma=None)
    assert extrator.processar_pdf("x.pdf") is base
    assert _Doc.criados == [("por", 300)]


def test_fatura_individual_nao_usa_o_fast(monkeypatch):
    r = Resultado()
    r.faturas = [{"id_fatura_agua": "F", "fornecedor": "DEMAE_PANAMA", "origem": "fatura", "competencia": "2021-01"}]
    _preparar(monkeypatch, {"por": r})
    assert extrator.processar_pdf("x.pdf") is r
    assert _Doc.criados == [("por", 300)]


def test_analitica_saneago_usa_o_fast_e_prefere_a_que_le_a_competencia(monkeypatch):
    base, fast = Resultado(), Resultado()
    base.faturas = [{"id_fatura_agua": "A", "fornecedor": "SANEAGO", "origem": "analitica", "competencia": None}]
    fast.faturas = [{"id_fatura_agua": "A", "fornecedor": "SANEAGO", "origem": "analitica", "competencia": "2021-01"},
                    {"id_fatura_agua": "B", "fornecedor": "SANEAGO", "origem": "analitica", "competencia": "2021-01"}]
    _preparar(monkeypatch, {"por": base, "por_fast": fast})
    assert extrator.processar_pdf("x.pdf") is fast


def test_falha_no_fast_mantem_a_leitura_e_avisa(monkeypatch):
    base = _bordero("SIM", 100.0)
    _preparar(monkeypatch, {"por": base})
    assert extrator.processar_pdf("x.pdf") is base        # KeyError em por_lang["por_fast"]
    assert any("por_fast falhou" in a for a in base.avisos)
