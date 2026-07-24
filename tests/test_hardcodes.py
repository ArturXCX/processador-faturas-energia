"""
Testes do motor de hardcodes (regras SE → ENTÃO do usuário), sem GUI.

Rodar:  PYTHONPATH=src python -m pytest tests/ -q
"""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from faturas_app.core import hardcodes  # noqa: E402


def _regra(aba, grupos, acoes, nome="teste", ativo=True):
    return {"id": "t", "nome": nome, "aba": aba, "ativo": ativo,
            "grupos": grupos, "acoes": acoes}


def test_grupos_ou_e_e():
    """O exemplo do requisito: SE (X=1 OU X=2) E (Y≠3) ENTÃO Z=0."""
    df = pd.DataFrame({"X": [1, 2, 3, 1, 2], "Y": [0, 0, 0, 3, 9], "Z": [9, 9, 9, 9, 9]})
    regra = _regra(
        "t",
        [{"operador": "OU", "condicoes": [
            {"coluna": "X", "operador": "igual", "valor": "1"},
            {"coluna": "X", "operador": "igual", "valor": "2"}]},
         {"operador": "E", "condicoes": [
             {"coluna": "Y", "operador": "diferente", "valor": "3"}]}],
        [{"coluna": "Z", "valor": "0"}])
    hardcodes.aplicar_dfs({"t": df}, [regra])
    assert list(df["Z"]) == [0, 0, 9, 9, 0]


def test_lista_e_comparacao_numerica_tolerante():
    """'não é nenhum de 30;50;100' casa números e textos indistintamente."""
    df = pd.DataFrame({"item": ["CONSUMO KWH"] * 4,
                       "quantidade": [30, "100", 254.0, "43"]})
    regra = _regra(
        "itens_fatura",
        [{"operador": "E", "condicoes": [
            {"coluna": "item", "operador": "igual", "valor": "CONSUMO KWH"},
            {"coluna": "quantidade", "operador": "nao_esta_em", "valor": "30;50;100"}]}],
        [{"coluna": "item", "valor": "CONSUMO"}])
    hardcodes.aplicar_dfs({"itens_fatura": df}, [regra])
    assert list(df["item"]) == ["CONSUMO KWH", "CONSUMO KWH", "CONSUMO", "CONSUMO"]


def test_nomes_de_aba_e_coluna_tolerantes():
    """'Postos Horários' deve casar com a coluna real 'Postos horarios'."""
    df = pd.DataFrame({"Grandezas": ["ENERGIA GERAÇÃO - KWH", "UFER"],
                       "Postos horarios": ["FORA PONTA", "FORA PONTA"],
                       "Consumo kWh": ["93.6", "27,06"]})
    regra = _regra(
        "MEDICAO",
        [{"operador": "E", "condicoes": [
            {"coluna": "grandezas", "operador": "igual", "valor": "energia geracao - kwh"},
            {"coluna": "Postos Horários", "operador": "igual", "valor": "FORA PONTA"}]}],
        [{"coluna": "consumo_kwh", "valor": "0"}])
    hardcodes.aplicar_dfs({"medicao": df}, [regra])
    assert list(df["Consumo kWh"]) == [0, "27,06"]


def test_regra_desativada_e_coluna_inexistente_nao_quebram():
    df = pd.DataFrame({"a": [1, 2]})
    fantasma = _regra("t", [{"operador": "E", "condicoes": [
        {"coluna": "nao_existe", "operador": "igual", "valor": "x"}]}],
        [{"coluna": "a", "valor": "9"}], nome="fantasma")
    desativada = _regra("t", [{"operador": "E", "condicoes": [
        {"coluna": "a", "operador": "igual", "valor": "1"}]}],
        [{"coluna": "a", "valor": "9"}], nome="off", ativo=False)
    rel = hardcodes.aplicar_dfs({"t": df}, [fantasma, desativada])
    assert list(df["a"]) == [1, 2]
    assert len(rel) == 1 and "não existe" in rel[0]


def test_operadores_de_texto_e_vazio():
    df = pd.DataFrame({"item": ["ADC BANDEIRA VERMELHA FP", "CONSUMO P"],
                       "obs": [None, "x"]})
    regra = _regra("t", [{"operador": "E", "condicoes": [
        {"coluna": "item", "operador": "contem", "valor": "bandeira"},
        {"coluna": "obs", "operador": "vazio", "valor": ""}]}],
        [{"coluna": "obs", "valor": "BANDEIRA"}])
    hardcodes.aplicar_dfs({"t": df}, [regra])
    assert list(df["obs"]) == ["BANDEIRA", "x"]


def test_hardcodes_padrao_sao_validos():
    """Os hardcodes que acompanham o app precisam estar completos."""
    padrao = hardcodes.padrao()
    assert padrao, "resources/hardcodes_padrao.json não foi carregado"
    for r in padrao:
        assert hardcodes.resumo_texto(r) != "(regra incompleta)", r["nome"]
        assert r["aba"] in hardcodes.abas_disponiveis(), r["aba"]


def test_caminho_saida_padrao():
    assert hardcodes.caminho_saida_padrao(os.path.join("d", "x.xlsx")) == \
        os.path.join("d", "x_hardcodes.xlsx")


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
