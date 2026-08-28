"""
Importação de hardcodes por planilha.

Existe porque o app deixou de embarcar as regras de UMA instituição e passou a
receber as de cada uma por importação. A leitura é TOLERANTE — quem monta a
planilha não vai acertar os rótulos exatos — e diz o que entendeu, em vez de
falhar em silêncio ou aceitar lixo.

(O mapa de UCs tem testes próprios em test_mapa_uc.py.)

Rodar:  PYTHONPATH=src python -m pytest tests/ -q
"""
import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from faturas_app.core import hardcodes  # noqa: E402


# ── hardcodes: planilha ──────────────────────────────────────────────────────
REGRA = {
    "id": "r1", "nome": "CONSUMO KWH atípico vira CONSUMO",
    "aba": "itens_fatura", "ativo": True,
    "grupos": [
        {"operador": "OU", "condicoes": [
            {"coluna": "item", "operador": "igual", "valor": "CONSUMO KWH"},
            {"coluna": "item", "operador": "igual", "valor": "CONSUMO ATIVO KWH"}]},
        {"operador": "E", "condicoes": [
            {"coluna": "quantidade", "operador": "nao_esta_em", "valor": "30;50;100"}]},
    ],
    "acoes": [{"coluna": "item", "valor": "CONSUMO"},
              {"coluna": "item_normalizado", "valor": "CONSUMO"}],
}


def test_ida_e_volta_preserva_a_regra(tmp_path):
    """Exportar e reimportar precisa devolver exatamente a mesma regra."""
    p = tmp_path / "hc.xlsx"
    assert hardcodes.exportar_planilha(str(p), [REGRA]) == 1
    regras, _rel = hardcodes.importar_planilha(str(p))
    assert regras == [hardcodes._normalizar(REGRA)]


def test_preserva_grupos_e_ligacoes(tmp_path):
    """A estrutura de parênteses (grupos) e o E/OU de cada um sobrevivem."""
    p = tmp_path / "hc.xlsx"
    hardcodes.exportar_planilha(str(p), [REGRA])
    regras, _ = hardcodes.importar_planilha(str(p))
    grupos = regras[0]["grupos"]
    assert len(grupos) == 2
    assert grupos[0]["operador"] == "OU" and len(grupos[0]["condicoes"]) == 2
    assert grupos[1]["operador"] == "E" and len(grupos[1]["condicoes"]) == 1


def _planilha(tmp_path, regras, acoes=None, nome="e.xlsx"):
    p = tmp_path / nome
    with pd.ExcelWriter(p, engine="openpyxl") as w:
        pd.DataFrame(regras).to_excel(w, sheet_name="hardcodes", index=False)
        if acoes is not None:
            pd.DataFrame(acoes).to_excel(w, sheet_name="acoes", index=False)
    return str(p)


def test_aceita_operador_pelo_rotulo_da_interface(tmp_path):
    """Quem monta a planilha à mão escreve 'é igual a', não 'igual'."""
    p = _planilha(tmp_path,
                  [{"id": "x", "nome": "R", "aba": "itens_fatura",
                    "coluna": "item", "operador": "é igual a", "valor": "A"}],
                  [{"id": "x", "coluna": "item", "valor": "B"}])
    regras, _ = hardcodes.importar_planilha(p)
    assert regras[0]["grupos"][0]["condicoes"][0]["operador"] == "igual"


def test_cabecalhos_com_acento_e_maiuscula(tmp_path):
    """'Coluna'/'OPERADOR'/'Ação' casam igual a 'coluna'/'operador'."""
    p = _planilha(tmp_path,
                  [{"ID": "x", "Nome": "R", "Aba": "itens_fatura",
                    "Coluna": "item", "OPERADOR": "igual", "Valor": "A"}],
                  [{"ID": "x", "Coluna": "item", "Valor": "B"}])
    regras, _ = hardcodes.importar_planilha(p)
    assert regras[0]["nome"] == "R"
    assert regras[0]["acoes"] == [{"coluna": "item", "valor": "B"}]


def test_ativo_aceita_varias_grafias(tmp_path):
    for bruto, esperado in (("SIM", True), ("nao", False), ("TRUE", True),
                            ("0", False), ("1", True), ("", True)):
        p = _planilha(tmp_path,
                      [{"id": "x", "nome": "R", "aba": "itens_fatura", "ativo": bruto,
                        "coluna": "item", "operador": "igual", "valor": "A"}],
                      [{"id": "x", "coluna": "item", "valor": "B"}],
                      nome=f"a{bruto or 'vazio'}.xlsx")
        regras, _ = hardcodes.importar_planilha(p)
        assert regras[0]["ativo"] is esperado, bruto


def test_operador_desconhecido_vira_aviso_e_nao_derruba(tmp_path):
    p = _planilha(tmp_path,
                  [{"id": "x", "nome": "R", "aba": "itens_fatura",
                    "coluna": "item", "operador": "igualzinho", "valor": "A"},
                   {"id": "y", "nome": "S", "aba": "itens_fatura",
                    "coluna": "item", "operador": "igual", "valor": "B"}],
                  [{"id": "y", "coluna": "item", "valor": "C"}])
    regras, rel = hardcodes.importar_planilha(p)
    assert [r["id"] for r in regras] == ["y"]          # a boa entrou
    assert any("igualzinho" in l for l in rel)         # e a ruim foi avisada


def test_regra_sem_acao_e_sinalizada(tmp_path):
    """Regra sem ENTÃO não muda nada — o usuário precisa saber disso."""
    p = _planilha(tmp_path,
                  [{"id": "x", "nome": "Sem acao", "aba": "itens_fatura",
                    "coluna": "item", "operador": "igual", "valor": "A"}])
    regras, rel = hardcodes.importar_planilha(p)
    assert regras[0]["acoes"] == []
    assert any("sem acao" in l.lower() for l in rel)


def test_arquivo_sem_colunas_minimas_e_recusado(tmp_path):
    p = _planilha(tmp_path, [{"qualquer": 1, "outra": 2}])
    with pytest.raises(ValueError):
        hardcodes.importar_planilha(p)


def test_csv_de_aba_unica(tmp_path):
    p = tmp_path / "hc.csv"
    pd.DataFrame([{"id": "x", "nome": "R", "aba": "itens_fatura",
                   "coluna": "item", "operador": "igual", "valor": "A"}]).to_csv(
        p, index=False)
    regras, _ = hardcodes.importar_planilha(str(p))
    assert regras[0]["nome"] == "R"


def test_dominio_borderos(tmp_path):
    """A importação respeita o domínio (abas de borderô, não de faturas)."""
    p = _planilha(tmp_path,
                  [{"id": "x", "nome": "R", "aba": "unidades",
                    "coluna": "valor", "operador": "igual", "valor": "0"}],
                  [{"id": "x", "coluna": "valor", "valor": "1"}])
    regras, _ = hardcodes.importar_planilha(p, "borderos")
    assert regras[0]["aba"] == "unidades"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
