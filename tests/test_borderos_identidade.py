"""
Identidade do borderô: número, agrupamento, competência e vencimento.

Antes tudo isso saía do NOME DO ARQUIVO, com o código de agrupamento do TJGO
(`4000000225`) escrito no regex — bastava renomear o PDF, ou ser de outra
instituição, para o borderô ficar sem identidade. Agora sai do CONTEÚDO, e o
nome do arquivo é só o último recurso.

Rodar:  PYTHONPATH=src python -m pytest tests/ -q
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from faturas_app.core import borderos  # noqa: E402


# ── id_bordero ───────────────────────────────────────────────────────────────
def test_id_com_numero():
    assert borderos._montar_id("EQUATORIAL", "4000000225008202400", "2024-08") == \
        "EQUATORIAL_4000000225008202400"


def test_id_sem_numero_usa_distribuidora_e_competencia():
    """Sem número aproveitável: DISTRIBUIDORA_AAAAMM (ex.: EQUATORIAL_202406)."""
    assert borderos._montar_id("EQUATORIAL", "", "2024-06") == "EQUATORIAL_202406"
    assert borderos._montar_id("ENEL", "", "2022-02") == "ENEL_202202"


def test_id_nunca_fica_vazio():
    """Sem número e sem competência ainda sai um id utilizável."""
    assert borderos._montar_id("EQUATORIAL", "", "") == "EQUATORIAL"
    assert borderos._montar_id("", "", "") == "BORDERO"


# ── distribuidora ────────────────────────────────────────────────────────────
def test_distribuidora_vem_do_conteudo():
    assert borderos._distribuidora("EQUATORIAL GOIÁS S.A.", "doc.pdf") == "EQUATORIAL"
    assert borderos._distribuidora("ENEL DISTRIBUIÇÃO GOIÁS", "doc.pdf") == "ENEL"
    assert borderos._distribuidora("CELG DISTRIBUIÇÃO", "doc.pdf") == "ENEL"


def test_distribuidora_cai_para_o_nome_do_arquivo():
    assert borderos._distribuidora("texto sem pista", "FATURA - EQUATORIAL - X.pdf") \
        == "EQUATORIAL"


def test_distribuidora_desconhecida_nao_quebra():
    assert borderos._distribuidora("texto neutro", "doc.pdf") == ""


# ── formatos ─────────────────────────────────────────────────────────────────
def test_competencia_em_ano_mes():
    """AAAA-MM, como no resto do app (antes era MM/AAAA e não cruzava)."""
    assert borderos._competencia_iso("8", "2024") == "2024-08"
    assert borderos._competencia_iso("12", "2022") == "2022-12"


# ── conjunto real (roda só quando os PDFs estão na máquina) ──────────────────
BASE = (r"J:\Meu Drive\UFG\Semestre Atual\TJGO\PBI sobre o projeto"
        r"\dashboard_faturas_energia\pdfs\borderos_energia_tjgo")
_tem_pdfs = os.path.isdir(BASE)
_motivo = "PDFs de borderô não estão nesta máquina"


@pytest.mark.skipif(not _tem_pdfs, reason=_motivo)
def test_identidade_sobrevive_a_renomear_o_arquivo(tmp_path):
    """
    O teste que fecha a mudança: copiado com um nome sem nenhuma informação,
    o borderô precisa sair idêntico — prova que a identidade vem do conteúdo.
    """
    import glob
    import shutil

    pdfs = sorted(glob.glob(os.path.join(BASE, "**", "*.pdf"), recursive=True))
    assert pdfs, "nenhum PDF de borderô encontrado"
    # um de cada layout: ENEL (2022) e EQUATORIAL (2024+)
    amostra = [p for p in pdfs if "ENEL" in p.upper()][:1] + \
              [p for p in pdfs if "EQUATORIAL" in p.upper()][-1:]
    # `distribuidora` fica de fora de propósito: em parte do acervo (todo 2022 e
    # jan–set/2023) a marca da concessionária NÃO está no texto do PDF — o
    # cabeçalho é imagem —, então ali o nome do arquivo é a única fonte. O
    # layout da tabela não serve de substituto: jun–set/2023 são EQUATORIAL
    # ainda usando o template da ENEL (transição da concessão).
    for orig in amostra:
        r0 = borderos.processar_pdf(orig)
        neutro = tmp_path / "documento_qualquer.pdf"
        shutil.copy(orig, neutro)
        r1 = borderos.processar_pdf(str(neutro))
        for campo in ("numero_fatura_agrupada", "competencia", "data_vencimento",
                      "cod_agrupamento", "valor_total",
                      "quantidade_contas_extraidas"):
            assert r0.bordero[campo] == r1.bordero[campo], (campo, orig)


@pytest.mark.skipif(not _tem_pdfs, reason=_motivo)
def test_acervo_reconcilia_e_tem_identidade():
    """
    Sobre o acervo inteiro: todo borderô tem id e competência, e a soma das UCs
    bate com o total impresso (menos os digitalizados, que não têm detalhe).
    """
    import glob
    import re

    pdfs = sorted(glob.glob(os.path.join(BASE, "**", "*.pdf"), recursive=True))
    nao_bate = []
    for p in pdfs:
        b = borderos.processar_pdf(p).bordero
        assert b["id_bordero"], p
        assert re.fullmatch(r"\d{4}-\d{2}", str(b["competencia"])), (p, b["competencia"])
        if b["data_vencimento"]:
            assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(b["data_vencimento"])), p
        if b["bate_total"] == "NÃO":
            nao_bate.append(os.path.basename(p))
    assert not nao_bate, f"borderôs que não reconciliam: {nao_bate}"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
