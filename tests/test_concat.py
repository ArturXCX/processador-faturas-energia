"""
Testes da lógica de concatenação/remapeamento (sem depender de PDFs).

Rodar:  PYTHONPATH=src python -m pytest tests/ -q
   ou:  PYTHONPATH=src python tests/test_concat.py
"""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from faturas_app.core import concat, schema  # noqa: E402


def _df(cols, linhas):
    return pd.DataFrame(linhas, columns=cols)


def test_concat_com_renomeacao_e_dedup():
    """Planilha enviada com coluna renomeada; novas faturas devem encaixar e dedup funcionar."""
    enviado = {
        "fatura": _df(["id_fatura", "Valor Total"],
                      [["A1", 100.0], ["A2", 200.0]]),
    }
    # mapa (como viria dos metadados): "Valor Total" -> "valor_total_r$"
    mapeamentos = {
        "fatura": {"id_fatura": "id_fatura", "Valor Total": "valor_total_r$"},
    }
    novos = {
        "fatura": _df(["id_fatura", "valor_total_r$"],
                      [["A2", 200.0], ["A3", 300.0]]),  # A2 é duplicata
    }
    res, meta, resumo = concat.concatenar(enviado, mapeamentos, novos)
    f = res["fatura"]
    assert list(f.columns) == ["id_fatura", "Valor Total"], "deve preservar nomes exibidos"
    assert len(f) == 3, "A2 duplicada deve ser removida (A1, A2, A3)"
    assert set(f["id_fatura"]) == {"A1", "A2", "A3"}


def test_concat_respeita_coluna_excluida():
    """Coluna removida da planilha enviada NÃO deve reaparecer (sem 'adicionar novas')."""
    enviado = {"fatura": _df(["id_fatura"], [["A1"]])}
    mapeamentos = {"fatura": {"id_fatura": "id_fatura"}}
    novos = {"fatura": _df(["id_fatura", "valor_total_r$"], [["A2", 50.0]])}
    res, _meta, _r = concat.concatenar(enviado, mapeamentos, novos,
                                       adicionar_novas_colunas=False)
    assert list(res["fatura"].columns) == ["id_fatura"]
    assert len(res["fatura"]) == 2


def test_concat_adicionar_novas_colunas():
    """Com a opção ligada, colunas novas entram ao final (linhas antigas vazias)."""
    enviado = {"fatura": _df(["id_fatura"], [["A1"]])}
    mapeamentos = {"fatura": {"id_fatura": "id_fatura"}}
    novos = {"fatura": _df(["id_fatura", "valor_total_r$"], [["A2", 50.0]])}
    res, _m, _r = concat.concatenar(enviado, mapeamentos, novos,
                                    adicionar_novas_colunas=True)
    assert "valor_total_r$" in res["fatura"].columns
    linha_a1 = res["fatura"][res["fatura"]["id_fatura"] == "A1"].iloc[0]
    assert pd.isna(linha_a1["valor_total_r$"])


def test_sugestao_mapeamento_e_apelido():
    """Auto-match reconhece nomes canônicos, a coluna link_pdf e apelidos."""
    cols = ["id_fatura", "valor_total_r$", "link_pdf", "url", "coluna_inventada"]
    sug = concat.sugerir_mapeamento("fatura", cols)
    assert sug["id_fatura"] == "id_fatura"
    assert sug["valor_total_r$"] == "valor_total_r$"
    assert sug["link_pdf"] == "link_pdf"          # coluna canônica própria
    # 'url' é apelido de link_pdf, mas link_pdf já foi consumido -> não remapeia 2x
    assert sug["url"] in (None, "link_pdf")
    assert sug["coluna_inventada"] is None


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"OK  {fn.__name__}")
    print(f"\n{len(fns)} teste(s) passaram.")
