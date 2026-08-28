"""
Mapa de Unidades Consumidoras: template, importação com mapeamento e efeito na
planilha.

O app não embarca cadastro de instituição nenhuma. O mapa é sempre importado, e
o que ele produz na planilha depende do que foi mapeado:

  - sem mapa: nenhuma coluna do template e, em aba nenhuma, `id_uc_canonico`;
  - item do template não mapeado: a coluna não é criada;
  - campo fora do template: vira coluna nova, com o nome escolhido.

`id_uc` é o único item obrigatório e precisa vir com esse nome exato — é a chave
de casamento com a fatura e não pode ser adivinhada.

Rodar:  PYTHONPATH=src python -m pytest tests/ -q
"""
import json
import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from faturas_app.core import derivados, dicionario_uc  # noqa: E402


@pytest.fixture(autouse=True)
def _isola(monkeypatch, tmp_path):
    """Mapa e configuração em pasta temporária — não toca no %APPDATA% real."""
    monkeypatch.setattr(dicionario_uc, "_dir_usuario", lambda: tmp_path)
    monkeypatch.setattr(dicionario_uc, "_CACHE", None)
    yield
    dicionario_uc.recarregar()


def _json(tmp_path, data, nome="m.json"):
    p = tmp_path / nome
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return str(p)


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


# ── template ─────────────────────────────────────────────────────────────────
def test_template_tem_a_chave_e_as_colunas_gerais():
    itens = [i for i, _c, _t, _d in dicionario_uc.TEMPLATE]
    assert itens[0] == "id_uc"
    assert set(dicionario_uc.COLUNAS_TEMPLATE) == {
        "id_uc_aneel_bordero", "uc_operante", "medidor_atual_dicionario",
        "unidade_institucional", "endereco_dicionario", "participa_rateio",
        "demanda_futura_kw"}


def test_template_nao_tem_demanda_contratada():
    """Demanda contratada vem sempre da fatura, nunca do cadastro."""
    itens = {i for i, _c, _t, _d in dicionario_uc.TEMPLATE}
    assert "demanda_contratada_kw" not in itens
    assert "demanda_geracao_contratada_kw" not in itens


def test_gerar_template_json_e_xlsx(tmp_path):
    pj = str(tmp_path / "t.json")
    dicionario_uc.gerar_template(pj)
    dados = json.loads(open(pj, encoding="utf-8").read())
    assert "id_uc" in dados["registros"][0]

    px = str(tmp_path / "t.xlsx")
    dicionario_uc.gerar_template(px)
    df = pd.read_excel(px)
    assert list(df.columns)[0] == "id_uc"


def test_template_gerado_e_reimportavel(tmp_path):
    """O modelo que o app entrega precisa ser aceito por ele mesmo."""
    p = str(tmp_path / "t.json")
    dicionario_uc.gerar_template(p)
    a = dicionario_uc.analisar_arquivo(p)
    assert a["pendentes"] == [] and a["sobrando"] == []


# ── importação ───────────────────────────────────────────────────────────────
def test_id_uc_e_obrigatorio_com_o_nome_exato(tmp_path):
    p = _json(tmp_path, [{"unidade_consumidora": "123", "unidade_institucional": "X"}])
    with pytest.raises(ValueError) as e:
        dicionario_uc.analisar_arquivo(p)
    assert "id_uc" in str(e.value)


def test_casamento_automatico_por_nome_identico(tmp_path):
    p = _json(tmp_path, [{"id_uc": "123", "unidade_institucional": "Fórum",
                          "uc_operante": True, "campo_estranho": "z"}])
    a = dicionario_uc.analisar_arquivo(p)
    assert a["auto"] == {"unidade_institucional": "unidade_institucional",
                         "uc_operante": "uc_operante"}
    assert "campo_estranho" in a["sobrando"]
    assert "endereco_dicionario" in a["pendentes"]


def test_item_pendente_nao_vira_coluna(tmp_path):
    p = _json(tmp_path, [{"id_uc": "123", "unidade_institucional": "Fórum"}])
    a = dicionario_uc.analisar_arquivo(p)
    regs, extras = dicionario_uc.aplicar_mapeamento(a)
    dicionario_uc.salvar_mapa(regs, extras)
    assert dicionario_uc.colunas_ativas() == ["unidade_institucional"]


def test_mapeamento_manual_resolve_pendencia(tmp_path):
    """Campo com outro nome vira coluna do template quando o usuário mapeia."""
    p = _json(tmp_path, [{"id_uc": "123", "orgao": "Fórum", "logradouro": "Rua A"}])
    a = dicionario_uc.analisar_arquivo(p)
    assert a["auto"] == {}
    regs, extras = dicionario_uc.aplicar_mapeamento(
        a, mapeamento={"unidade_institucional": "orgao",
                       "endereco_dicionario": "logradouro"})
    dicionario_uc.salvar_mapa(regs, extras)
    assert set(dicionario_uc.colunas_ativas()) == {"unidade_institucional",
                                                   "endereco_dicionario"}
    c = dicionario_uc.campos_unidade_consumidora("123")
    assert c["unidade_institucional"] == "Fórum"
    assert c["endereco_dicionario"] == "Rua A"


def test_campo_fora_do_template_vira_coluna_nova(tmp_path):
    p = _json(tmp_path, [{"id_uc": "123", "centro_de_custo": "CC-9"}])
    a = dicionario_uc.analisar_arquivo(p)
    regs, extras = dicionario_uc.aplicar_mapeamento(
        a, extras={"centro_de_custo": "centro_de_custo"})
    dicionario_uc.salvar_mapa(regs, extras)
    assert "centro_de_custo" in dicionario_uc.colunas_ativas()
    assert dicionario_uc.campos_unidade_consumidora("123")["centro_de_custo"] == "CC-9"


def test_coluna_nova_pode_receber_nome_manual(tmp_path):
    p = _json(tmp_path, [{"id_uc": "123", "cc": "CC-9"}])
    a = dicionario_uc.analisar_arquivo(p)
    regs, extras = dicionario_uc.aplicar_mapeamento(a, extras={"cc": "centro_de_custo"})
    dicionario_uc.salvar_mapa(regs, extras)
    assert dicionario_uc.campos_unidade_consumidora("123")["centro_de_custo"] == "CC-9"


def test_demanda_contratada_nunca_entra_nem_como_extra(tmp_path):
    """BLINDAGEM: o campo é recusado mesmo que o usuário tente mapeá-lo."""
    p = _json(tmp_path, [{"id_uc": "123", "demanda_contratada_kw": 150}])
    a = dicionario_uc.analisar_arquivo(p)
    assert "demanda_contratada_kw" not in a["sobrando"]
    assert any("demanda" in x.lower() for x in a["avisos"])
    regs, extras = dicionario_uc.aplicar_mapeamento(
        a, extras={"demanda_contratada_kw": "demanda_contratada_kw"})
    dicionario_uc.salvar_mapa(regs, extras)
    assert "demanda_contratada_kw" not in dicionario_uc.colunas_ativas()


def test_varios_ids_na_mesma_uc(tmp_path):
    """Formato antigo e novo no mesmo registro: os dois casam, o 1º é canônico."""
    p = _json(tmp_path, [{"id_uc": "10008414082; 2.742.876.012-19",
                          "unidade_institucional": "Juizado"}])
    a = dicionario_uc.analisar_arquivo(p)
    dicionario_uc.salvar_mapa(*dicionario_uc.aplicar_mapeamento(a))
    assert dicionario_uc.buscar("10008414082") is not None
    assert dicionario_uc.buscar("2.742.876.012-19") is not None
    assert dicionario_uc.id_canonico("2.742.876.012-19") == "10008414082"


def test_importar_planilha_em_vez_de_json(tmp_path):
    p = tmp_path / "m.xlsx"
    pd.DataFrame([{"id_uc": "123", "unidade_institucional": "Fórum"}]).to_excel(
        p, index=False)
    a = dicionario_uc.analisar_arquivo(str(p))
    assert a["auto"] == {"unidade_institucional": "unidade_institucional"}


# ── efeito na planilha ───────────────────────────────────────────────────────
def _carregar_mapa(tmp_path, registros, **kw):
    p = _json(tmp_path, registros, nome="mp.json")
    a = dicionario_uc.analisar_arquivo(p)
    dicionario_uc.salvar_mapa(*dicionario_uc.aplicar_mapeamento(a, **kw))


def test_sem_mapa_nao_ha_canonico_nem_colunas():
    """O caso mais importante: sem mapa, a planilha não ganha nada do template."""
    assert dicionario_uc.ativo() is False
    dfs = _dfs()
    derivados.aplicar(dfs)
    for aba, df in dfs.items():
        assert "id_uc_canonico" not in df.columns, aba
    uc = dfs["unidade_consumidora"]
    for col in dicionario_uc.COLUNAS_TEMPLATE:
        assert col not in uc.columns, col


def test_com_mapa_ha_canonico_em_todas_as_abas(tmp_path):
    _carregar_mapa(tmp_path, [{"id_uc": "10008414082; 2.742.876.012-19",
                               "unidade_institucional": "Juizado"}])
    dfs = _dfs()
    derivados.aplicar(dfs)
    for aba, df in dfs.items():
        if "id_uc" in df.columns:
            assert "id_uc_canonico" in df.columns, aba
    uc = dfs["unidade_consumidora"]
    assert list(uc["id_uc_canonico"]) == ["10008414082", "10008414082"]
    assert list(uc["unidade_institucional"]) == ["Juizado", "Juizado"]


def test_colunas_do_template_nao_mapeadas_ficam_fora(tmp_path):
    _carregar_mapa(tmp_path, [{"id_uc": "10008414082", "unidade_institucional": "X"}])
    dfs = _dfs()
    derivados.aplicar(dfs)
    uc = dfs["unidade_consumidora"]
    assert "unidade_institucional" in uc.columns
    for col in ("endereco_dicionario", "uc_operante", "demanda_futura_kw"):
        assert col not in uc.columns, col


def test_unidade_judiciaria_virou_unidade_institucional():
    assert "unidade_institucional" in dicionario_uc.COLUNAS_TEMPLATE
    assert "unidade_judiciaria" not in dicionario_uc.COLUNAS_TEMPLATE


# ── identificação por medidor: opcional quando há mapa ───────────────────────
def test_sem_mapa_o_medidor_e_sempre_usado():
    """Sem cadastro, a heurística de medidor é a única identificação que há."""
    assert dicionario_uc.usar_medidor() is True
    dicionario_uc.definir_usar_medidor(False)
    assert dicionario_uc.usar_medidor() is True     # ignorado sem mapa


def test_com_mapa_o_medidor_pode_ser_desligado(tmp_path):
    _carregar_mapa(tmp_path, [{"id_uc": "10008414082; 2.742.876.012-19"}])
    dicionario_uc.definir_usar_medidor(False)
    assert dicionario_uc.usar_medidor() is False

    dfs = _dfs()
    derivados.aplicar(dfs)
    for aba, df in dfs.items():
        for col in ("id_uc_atual_medidor", "id_uc_atual_medidor_sem_format",
                    "id_uc_atual"):
            assert col not in df.columns, (aba, col)
    # o canônico continua, vindo do mapa
    assert list(dfs["unidade_consumidora"]["id_uc_canonico"]) == ["10008414082"] * 2


def test_com_mapa_e_medidor_ligado_as_colunas_ficam(tmp_path):
    _carregar_mapa(tmp_path, [{"id_uc": "10008414082; 2.742.876.012-19"}])
    dicionario_uc.definir_usar_medidor(True)
    dfs = _dfs()
    derivados.aplicar(dfs)
    assert "id_uc_atual_medidor" in dfs["unidade_consumidora"].columns
    assert "id_uc_atual" in dfs["fatura"].columns


def test_uc_fora_do_mapa_cai_no_medidor(tmp_path):
    _carregar_mapa(tmp_path, [{"id_uc": "99999999"}])
    dicionario_uc.definir_usar_medidor(True)
    dfs = _dfs()
    derivados.aplicar(dfs)
    uc = dfs["unidade_consumidora"]
    # nenhuma das duas UCs está no mapa -> canônico vem do medidor
    assert list(uc["id_uc_canonico"]) == list(uc["id_uc_atual_medidor_sem_format"])


def test_limpar_mapa_volta_ao_estado_sem_mapa(tmp_path):
    _carregar_mapa(tmp_path, [{"id_uc": "10008414082"}])
    assert dicionario_uc.ativo() is True
    dicionario_uc.limpar_mapa()
    assert dicionario_uc.ativo() is False
    assert dicionario_uc.colunas_ativas() == []


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
