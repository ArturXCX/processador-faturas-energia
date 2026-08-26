"""
Metodologia de identificação de Unidade Consumidora.

O dicionário oficial é o cadastro de UMA instituição. Um app que dependesse só
dele não serviria a nenhuma outra, cujas UCs não estão no arquivo — por isso a
metodologia é escolhida pelo usuário e fica persistida:

  MODO_DICIONARIO — cadastro e `id_uc_canonico` vêm do JSON oficial.
  MODO_MEDIDOR    — comportamento CLÁSSICO: tudo do PDF, reconciliação pelo
                    medidor, e as colunas do dicionário nem são criadas.

Rodar:  PYTHONPATH=src python -m pytest tests/ -q
"""
import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from faturas_app.core import derivados, dicionario_uc  # noqa: E402

# Mesma UC real, em dois formatos de id_uc, com o MESMO medidor nas duas
# faturas — assim a heurística de medidor também consegue uni-las e dá para
# comparar as duas metodologias no mesmo lote.
REGISTROS = [{
    "UC": 274287601219,
    "UC FORMATADO (PARA ENCONTRAR UCs NAS FATURAS DA EQUATORIAL)": "2.742.876.012-19",
    "UC VELHA": 10008414082,
    "OPERANTE": True,
    "MEDIDORES_UTILIZADOS": ["10517719-9"],
    "MEDIDOR_ATUAL": "10517719-9",
    "UNIDADE JUDICIÁRIA": "Juizado de Anápolis",
    "COMARCA": "Anápolis",
}]


@pytest.fixture(autouse=True)
def _isola(monkeypatch, tmp_path):
    """Dicionário sintético + config em pasta temporária (não toca no %APPDATA%)."""
    cache = dicionario_uc._construir(REGISTROS)
    cache["fonte"], cache["arquivo"] = "semente", None
    monkeypatch.setattr(dicionario_uc, "_CACHE", cache)
    monkeypatch.setattr(dicionario_uc, "_dir_usuario", lambda: tmp_path)
    yield


def _dfs():
    return {
        "fatura": pd.DataFrame({
            "id_fatura": ["EQUATORIAL_1", "EQUATORIAL_2"],
            "id_uc": ["10008414082", "2.742.876.012-19"],
            "competencia": ["2022-03", "2025-07"],
            "fornecedor": ["EQUATORIAL", "EQUATORIAL"]}),
        "unidade_consumidora": pd.DataFrame({
            "id_uc": ["10008414082", "2.742.876.012-19"]}),
        "medicao": pd.DataFrame({
            "id_fatura": ["EQUATORIAL_1", "EQUATORIAL_2"],
            "id_uc": ["10008414082", "2.742.876.012-19"],
            "competencia": ["2022-03", "2025-07"],
            "Medidor": ["10517719-9", "10517719-9"]}),
    }


def test_padrao_e_o_medidor():
    """
    Instalação nova nasce SEM cadastro (o app não embarca dicionário nenhum),
    então a metodologia que funciona sem cadastro é a única que faz sentido
    como padrão. Importar um JSON liga o modo dicionário sozinho.
    """
    assert dicionario_uc.modo() == dicionario_uc.MODO_MEDIDOR
    assert dicionario_uc.ativo() is False


def test_escolha_persiste():
    dicionario_uc.definir_modo(dicionario_uc.MODO_MEDIDOR)
    assert dicionario_uc.modo() == dicionario_uc.MODO_MEDIDOR
    assert dicionario_uc.ativo() is False
    dicionario_uc.definir_modo(dicionario_uc.MODO_DICIONARIO)
    assert dicionario_uc.ativo() is True


def test_modo_invalido_e_recusado():
    with pytest.raises(ValueError):
        dicionario_uc.definir_modo("telepatia")


def test_com_dicionario_traz_o_cadastro():
    dicionario_uc.definir_modo(dicionario_uc.MODO_DICIONARIO)
    dfs = _dfs()
    derivados.aplicar(dfs)
    uc = dfs["unidade_consumidora"]
    assert "unidade_judiciaria" in uc.columns
    assert uc["unidade_judiciaria"].iat[0] == "Juizado de Anápolis"
    assert list(uc["id_uc_canonico"]) == ["274287601219", "274287601219"]


def test_sem_dicionario_nao_cria_as_colunas_de_cadastro():
    """
    O ponto da mudança: numa instituição sem cadastro oficial, a planilha não
    pode vir cheia de colunas vazias de um cadastro que não é dela.
    """
    dicionario_uc.definir_modo(dicionario_uc.MODO_MEDIDOR)
    dfs = _dfs()
    derivados.aplicar(dfs)
    uc = dfs["unidade_consumidora"]
    for col in dicionario_uc.COLUNAS_UNIDADE_CONSUMIDORA:
        assert col not in uc.columns, col


def test_sem_dicionario_usa_o_medidor_no_canonico():
    """Sem cadastro, id_uc_canonico é a UC inferida pelo MEDIDOR (método antigo)."""
    dicionario_uc.definir_modo(dicionario_uc.MODO_MEDIDOR)
    dfs = _dfs()
    derivados.aplicar(dfs)
    uc = dfs["unidade_consumidora"]
    assert list(uc["id_uc_canonico"]) == list(uc["id_uc_atual_medidor_sem_format"])
    # as duas faturas compartilham o medidor, então a heurística antiga também
    # une as duas linhas
    assert len(set(uc["id_uc_canonico"])) == 1


def test_sem_dicionario_o_cadastro_do_pdf_continua():
    """Sem dicionário, o que vem do PDF continua vindo do PDF."""
    dicionario_uc.definir_modo(dicionario_uc.MODO_MEDIDOR)
    dfs = _dfs()
    dfs["unidade_consumidora"]["razao_social"] = ["TJGO", "TJGO"]
    derivados.aplicar(dfs)
    assert list(dfs["unidade_consumidora"]["razao_social"]) == ["TJGO", "TJGO"]


def test_sem_dicionario_o_canonico_existe_em_todas_as_abas():
    dicionario_uc.definir_modo(dicionario_uc.MODO_MEDIDOR)
    dfs = _dfs()
    derivados.aplicar(dfs)
    for aba, df in dfs.items():
        if "id_uc" in df.columns:
            assert "id_uc_canonico" in df.columns, aba


def test_trocar_de_modo_nao_deixa_residuo():
    """Rodar com dicionário e depois sem: as colunas antigas não podem sobrar."""
    dicionario_uc.definir_modo(dicionario_uc.MODO_DICIONARIO)
    dfs = _dfs()
    derivados.aplicar(dfs)
    assert "unidade_judiciaria" in dfs["unidade_consumidora"].columns

    dicionario_uc.definir_modo(dicionario_uc.MODO_MEDIDOR)
    dfs2 = _dfs()                      # lote novo, como um processamento novo
    derivados.aplicar(dfs2)
    assert "unidade_judiciaria" not in dfs2["unidade_consumidora"].columns


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
