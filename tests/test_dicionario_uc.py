"""
Testes do dicionário oficial de Unidades Consumidoras (core/dicionario_uc.py) e
do enriquecimento que ele faz na aba 'unidade_consumidora' (derivados.py).

Os testes usam um dicionário SINTÉTICO (injetado no cache do módulo), nunca a
semente embutida — assim não dependem do cadastro real nem quebram quando ele é
atualizado.

O teste mais importante daqui é `test_campos_nunca_traz_demanda_contratada`: a
demanda contratada precisa vir SEMPRE da fatura, nunca do cadastro, e a
blindagem contra isso é estrutural (tabela explícita campo→coluna).

Rodar:  PYTHONPATH=src python -m pytest tests/ -q
"""
import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from faturas_app.core import derivados, dicionario_uc  # noqa: E402

# ── Dicionário sintético ─────────────────────────────────────────────────────
# 1) UC com formato novo + UC VELHA diferente + 1 medidor
# 2) UC sem "UC FORMATADO" (só numérica) + 2 medidores
# 3) UC com formatação e sem UC VELHA
REGISTROS = [
    {
        "UC": 274287601219,
        "UC FORMATADO (PARA ENCONTRAR UCs NAS FATURAS DA EQUATORIAL)": "2.742.876.012-19",
        "UC RESOLUÇÃO Nº 1095/2024 ANEEL (BORDERÔ)": "000274287601219",
        "UC VELHA": 10008414082,
        "OPERANTE": True,
        "MEDIDORES_UTILIZADOS": ["10517719-9"],
        "MEDIDOR_ATUAL": "10517719-9",
        "UNIDADE JUDICIÁRIA": "Juizado de Anápolis",
        "CONCESSIONÁRIA": "EQUATORIAL",
        "COMARCA": "Anápolis",
        "GD (GERAÇÃO DISTRIBUÍDA)": False,
        "PARTICIPA DOS RATEIOS DE ALGUMA FORMA": False,
    },
    {
        "UC": 31811020,
        "UC VELHA": 990001,
        "OPERANTE": True,
        "MEDIDORES_UTILIZADOS": ["A-1", "B-2"],
        "MEDIDOR_ATUAL": "B-2",
        "UNIDADE JUDICIÁRIA": "Fórum de Ceres",
        "CONCESSIONÁRIA": "CHESP",
        "COMARCA": "Ceres",
        "PARTICIPA DOS RATEIOS DE ALGUMA FORMA": True,
        "PORCENTAGEM (%)": "5%",
        "Saldos do SCEE (GDs)": 1234.5,
    },
    {
        "UC": 4289401203,
        "UC FORMATADO (PARA ENCONTRAR UCs NAS FATURAS DA EQUATORIAL)": "42.894.012-03",
        "OPERANTE": False,
        "MEDIDORES_UTILIZADOS": [],
        "UNIDADE JUDICIÁRIA": "Anexo Rua 18",
        "CONCESSIONÁRIA": "EQUATORIAL",
    },
]


@pytest.fixture(autouse=True)
def _dicionario_sintetico(monkeypatch):
    """Injeta REGISTROS no cache do módulo, isolando os testes do cadastro real."""
    cache = dicionario_uc._construir(REGISTROS)
    cache["fonte"] = "semente"
    cache["arquivo"] = None
    monkeypatch.setattr(dicionario_uc, "_CACHE", cache)
    yield


# ── buscar() ─────────────────────────────────────────────────────────────────
def test_busca_pelo_formato_atual():
    assert dicionario_uc.buscar(274287601219)["UNIDADE JUDICIÁRIA"] == "Juizado de Anápolis"
    assert dicionario_uc.buscar("274287601219")["UNIDADE JUDICIÁRIA"] == "Juizado de Anápolis"


def test_busca_pelo_formato_antigo():
    """UC VELHA e UC apontam para o MESMO registro — é isso que une o histórico."""
    assert dicionario_uc.buscar(10008414082)["UC"] == 274287601219


def test_busca_pelo_uc_formatado_com_e_sem_pontuacao():
    assert dicionario_uc.buscar("2.742.876.012-19")["UC"] == 274287601219
    assert dicionario_uc.buscar("42.894.012-03")["UC"] == 4289401203
    assert dicionario_uc.buscar("4289401203")["UC"] == 4289401203


def test_busca_desconhecida_devolve_none_sem_excecao():
    assert dicionario_uc.buscar("999999999999") is None
    assert dicionario_uc.buscar(None) is None
    assert dicionario_uc.buscar("") is None
    assert dicionario_uc.buscar("NULO_EQUATORIAL_123") is None


# ── campos_unidade_consumidora() ─────────────────────────────────────────────
def test_campos_nunca_traz_demanda_contratada():
    """
    BLINDAGEM (o teste mais importante deste arquivo): mesmo que o registro do
    dicionário TRAGA os campos de demanda contratada, eles não podem virar
    coluna — demanda contratada vem sempre da fatura, nunca do cadastro.
    """
    reg = dict(REGISTROS[0])
    reg["DEMANDA CONTRATADA (kW)"] = 150
    reg["DEMANDA GERAÇÃO (kW)"] = 90
    cache = dicionario_uc._construir([reg])
    cache["fonte"], cache["arquivo"] = "semente", None
    dicionario_uc._CACHE = cache

    campos = dicionario_uc.campos_unidade_consumidora(274287601219)
    assert "demanda_contratada_kw" not in campos
    assert "demanda_geracao_contratada_kw" not in campos
    assert 150 not in campos.values()
    assert 90 not in campos.values()
    # e o app avisa que o campo voltou a aparecer, em vez de ignorar em silêncio
    assert any("DEMANDA CONTRATADA" in a for a in dicionario_uc.avisos())


def test_campos_devolve_exatamente_as_colunas_declaradas():
    campos = dicionario_uc.campos_unidade_consumidora(274287601219)
    assert sorted(campos) == sorted(dicionario_uc.COLUNAS_UNIDADE_CONSUMIDORA)
    assert len(dicionario_uc.COLUNAS_UNIDADE_CONSUMIDORA) == 28


def test_campos_tipos_e_valores():
    c = dicionario_uc.campos_unidade_consumidora("2.742.876.012-19")
    assert c["id_uc_dicionario"] == "2.742.876.012-19"
    assert c["id_uc_dicionario_sem_format"] == "274287601219"
    assert c["id_uc_antigo_dicionario"] == "10008414082"
    assert c["uc_operante"] is True                     # booleano nativo
    assert c["possui_geracao_distribuida"] is False
    assert c["comarca"] == "Anápolis"
    # campo esparso ausente neste registro -> None (não string "None")
    assert c["percentual_rateio"] is None


def test_campos_sem_uc_formatado_cai_para_a_uc_numerica():
    c = dicionario_uc.campos_unidade_consumidora(31811020)
    assert c["id_uc_dicionario"] == "31811020"
    assert c["saldo_scee_cadastro_kwh"] == 1234.5       # número, não texto
    assert c["percentual_rateio"] == "5%"


def test_medidores_utilizados_vira_texto_unido():
    assert dicionario_uc.campos_unidade_consumidora(31811020)[
        "medidores_utilizados_dicionario"] == "A-1; B-2"
    assert dicionario_uc.campos_unidade_consumidora(274287601219)[
        "medidores_utilizados_dicionario"] == "10517719-9"
    # lista vazia -> string vazia (o campo existe no cadastro, só não tem medidor)
    assert dicionario_uc.campos_unidade_consumidora(4289401203)[
        "medidores_utilizados_dicionario"] == ""


def test_campos_uc_desconhecida_devolve_none():
    assert dicionario_uc.campos_unidade_consumidora("999999999999") is None


# ── metadados() / avisos() ───────────────────────────────────────────────────
def test_metadados():
    m = dicionario_uc.metadados()
    assert m["total_ucs"] == 3
    assert m["operantes"] == 2
    assert m["fonte"] == "semente"


def test_colisao_vira_aviso_e_nao_derruba_o_processamento():
    """Dois registros reivindicando o mesmo número: avisa e mantém o primeiro."""
    colidem = [
        {"UC": 111222333, "UNIDADE JUDICIÁRIA": "Primeiro"},
        {"UC": 444555666, "UC VELHA": 111222333, "UNIDADE JUDICIÁRIA": "Segundo"},
    ]
    cache = dicionario_uc._construir(colidem)
    cache["fonte"], cache["arquivo"] = "semente", None
    dicionario_uc._CACHE = cache

    assert any("111222333" in a for a in dicionario_uc.avisos())
    assert dicionario_uc.buscar(111222333)["UNIDADE JUDICIÁRIA"] == "Primeiro"


def test_campo_nao_mapeado_vira_aviso():
    cache = dicionario_uc._construir([{"UC": 1, "CAMPO NOVO INVENTADO": "x"}])
    cache["fonte"], cache["arquivo"] = "semente", None
    dicionario_uc._CACHE = cache
    assert any("CAMPO NOVO INVENTADO" in a for a in dicionario_uc.avisos())


# ── validar_estrutura() (usado na importação pela aba Parâmetros) ────────────
def test_validar_estrutura():
    dicionario_uc.validar_estrutura([{"UC": 1}])            # não levanta
    with pytest.raises(ValueError):
        dicionario_uc.validar_estrutura({"UC": 1})          # objeto, não lista
    with pytest.raises(ValueError):
        dicionario_uc.validar_estrutura([])                 # lista vazia
    with pytest.raises(ValueError):
        dicionario_uc.validar_estrutura([{"SEM_UC": 1}])    # registro sem 'UC'


# ── derivados._enriquecer_dicionario_uc ──────────────────────────────────────
def _dfs_sinteticos(id_uc_uc, id_uc_fatura=None):
    id_uc_fatura = id_uc_fatura or id_uc_uc
    return {
        "fatura": pd.DataFrame({
            "id_fatura": ["EQUATORIAL_1"], "id_uc": [id_uc_fatura],
            "competencia": ["2024-01"], "fornecedor": ["EQUATORIAL"]}),
        "unidade_consumidora": pd.DataFrame({
            "id_uc": [id_uc_uc], "razao_social": ["TJGO"]}),
    }


def test_enriquecer_preenche_as_28_colunas_na_uc():
    dfs = _dfs_sinteticos("2.742.876.012-19")
    derivados._colunas_medidor(dfs)
    derivados._enriquecer_dicionario_uc(dfs)
    uc = dfs["unidade_consumidora"]
    for col in dicionario_uc.COLUNAS_UNIDADE_CONSUMIDORA:
        assert col in uc.columns, col
    assert uc["unidade_judiciaria"].iat[0] == "Juizado de Anápolis"
    assert uc["id_uc_canonico"].iat[0] == "274287601219"


def test_id_uc_canonico_une_formatos_diferentes_da_mesma_uc():
    """Formato antigo e novo da MESMA UC real convergem para o mesmo canônico."""
    novo = _dfs_sinteticos("2.742.876.012-19")
    antigo = _dfs_sinteticos("10008414082")
    for dfs in (novo, antigo):
        derivados._colunas_medidor(dfs)
        derivados._enriquecer_dicionario_uc(dfs)
    assert (novo["unidade_consumidora"]["id_uc_canonico"].iat[0]
            == antigo["unidade_consumidora"]["id_uc_canonico"].iat[0]
            == "274287601219")


def test_id_uc_canonico_cai_para_o_medidor_quando_desconhecida():
    """UC fora do dicionário: mantém a heurística de medidor como fallback."""
    dfs = _dfs_sinteticos("88888888")
    derivados._colunas_medidor(dfs)
    derivados._enriquecer_dicionario_uc(dfs)
    uc = dfs["unidade_consumidora"]
    assert uc["id_uc_canonico"].iat[0] == uc["id_uc_atual_medidor_sem_format"].iat[0]
    assert uc["unidade_judiciaria"].iat[0] is None


def test_demais_abas_recebem_so_o_canonico():
    """fatura/itens/medicao não devem carregar o cadastro repetido por linha."""
    dfs = _dfs_sinteticos("2.742.876.012-19")
    derivados._colunas_medidor(dfs)
    derivados._enriquecer_dicionario_uc(dfs)
    fat = dfs["fatura"]
    assert fat["id_uc_canonico"].iat[0] == "274287601219"
    assert "unidade_judiciaria" not in fat.columns
    assert "medidor_atual_dicionario" not in fat.columns


def test_extremos_agrupam_por_canonico_mesmo_com_id_uc_mudando():
    """
    Uma UC que aparece nos DOIS formatos ao longo do tempo tem um único
    intervalo de competências, não dois pela metade.
    """
    dfs = {
        "fatura": pd.DataFrame({
            "id_fatura": ["EQUATORIAL_1", "EQUATORIAL_2"],
            "id_uc": ["10008414082", "2.742.876.012-19"],
            "competencia": ["2022-03", "2025-07"],
            "fornecedor": ["EQUATORIAL", "EQUATORIAL"]}),
        "unidade_consumidora": pd.DataFrame({
            "id_uc": ["10008414082", "2.742.876.012-19"]}),
    }
    derivados._calcular(dfs)
    uc = dfs["unidade_consumidora"]
    assert list(uc["primeira_competencia"]) == ["2022-03", "2022-03"]
    assert list(uc["ultima_competencia"]) == ["2025-07", "2025-07"]
    assert list(uc["primeira_fatura"]) == ["EQUATORIAL_1", "EQUATORIAL_1"]


def test_concat_iguala_uc_em_formatos_diferentes():
    """
    Regressão de concatenação: planilha "enviada" com a UC em formato antigo +
    fatura nova da mesma UC em formato novo. id_uc_canonico precisa igualar as
    duas linhas mesmo com id_uc diferente.
    """
    res_dfs = {
        "fatura": pd.DataFrame({
            "id_fatura": ["EQUATORIAL_1", "EQUATORIAL_2"],
            "id_uc": ["10008414082", "2.742.876.012-19"],
            "competencia": ["2022-03", "2025-07"],
            "fornecedor": ["EQUATORIAL", "EQUATORIAL"]}),
        "unidade_consumidora": pd.DataFrame({
            "id_uc": ["10008414082", "2.742.876.012-19"]}),
    }
    derivados.aplicar_concat(res_dfs, None)
    canon = list(res_dfs["fatura"]["id_uc_canonico"])
    assert canon == ["274287601219", "274287601219"]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
