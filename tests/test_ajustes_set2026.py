"""
Ajustes de setembro/2026, com trechos REAIS de texto de fatura:

  - Equatorial: demanda contratada = 0 quando a UC é faturada "S/ CONTRATO";
    coluna `mensagens_importantes`; detecção do texto embaralhado do layout 2022.
  - CHESP: `data_emissao` com o rótulo quebrado em duas linhas (193/203 faturas
    saíam vazias); demanda contratada com o rótulo corrompido pelo OCR e o
    fallback pelo item "DEMANDA kW"; `mensagens_importantes`; emissão do Modelo 6.
  - Aba `validacao` (derivados._derivar_validacao).
  - Mapa de UCs: chave escolhível e identificadores alternativos ('UC VELHA').
  - Modo linha de comando: fornecedora inferida pelo caminho.

Rodar:  PYTHONPATH=src python -m pytest tests/ -q
"""
import json
import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from faturas_app import cli  # noqa: E402
from faturas_app.core import chesp, derivados, dicionario_uc, equatorial  # noqa: E402


@pytest.fixture(autouse=True)
def _isola(monkeypatch, tmp_path):
    monkeypatch.setattr(dicionario_uc, "_dir_usuario", lambda: tmp_path)
    monkeypatch.setattr(dicionario_uc, "_CACHE", None)
    yield
    dicionario_uc.recarregar()


# ── Equatorial: demanda ──────────────────────────────────────────────────────
def test_eq_sem_contrato_demanda_zero():
    """UC 10037643922 (ago–dez/2023): caixa de grandezas contratadas vazia e
    itens 'S/ CONTRATO' — é 0, não vazio."""
    txt = ("Classificação: A A4 PODER PÚBLICO - ESTADUAL THS_VERDE Tipo de Fornecimento: TRIFÁSICO\n"
           "CONSUMO S/ CONTRATO FP kWh 2440,20 0,430653 1.050,88 45,15 1050,88 0% 0 0,412150\n"
           "DEMANDA S/ CONTRATO FP kW 15,79 23,969865 378,53 16,26 378,53 0% 0 22,940000\n")
    fat = equatorial.extrair_fatura(txt, "x.pdf", numero_forcado="1")
    assert fat["demanda_contratada_kw"] == 0.0


def test_eq_caixa_presente_vence_o_sem_contrato():
    txt = "DEMANDA - kW 60\nCONSUMO S/ CONTRATO FP kWh 1 1 1\n"
    fat = equatorial.extrair_fatura(txt, "x.pdf", numero_forcado="1")
    assert fat["demanda_contratada_kw"] == 60.0


def test_eq_sem_caixa_e_sem_contrato_continua_nulo():
    txt = "Classificação: B B3 CONVENCIONAL\nCONSUMO kWh 100 0,9 90\n"
    fat = equatorial.extrair_fatura(txt, "x.pdf", numero_forcado="1")
    assert fat["demanda_contratada_kw"] is None


# ── Equatorial: mensagens importantes ────────────────────────────────────────
def test_eq_mensagens_layout_2025():
    txt = ("CFOP 5258: Venda de energia elétrica para não contribuinte\n"
           "JUL/2026 R$**********96,87 30/08/2026\n"
           "PERÍODO DE REFERÊNCIA DA APURAÇÃO DOS INDICADORES DE CONTINUIDADE = 5/2026. VRC = R$ 919,34955\n"
           "PIS/PASEP 98,05 1,267% 1,24\n")
    assert equatorial.extrair_mensagens(txt) == (
        "PERÍODO DE REFERÊNCIA DA APURAÇÃO DOS INDICADORES DE CONTINUIDADE = 5/2026. "
        "VRC = R$ 919,34955")


def test_eq_mensagens_layout_2023_duas_linhas():
    txt = ("AGO/2023 30/09/2023 R$*******6.680,53\n"
           "ATRASO NO PAGAMENTO: AS CONTAS NÃO PAGAS ATÉ A DATA DE VENCIMENTO SOFRERÃO MULTA\n"
           "NA FATURA SEGUINTE A REALIZAÇÃO DO PAGAMENTO.\n"
           "PIS/PASEP 3103,12 0,7664% 23,78\n")
    assert equatorial.extrair_mensagens(txt) == (
        "ATRASO NO PAGAMENTO: AS CONTAS NÃO PAGAS ATÉ A DATA DE VENCIMENTO SOFRERÃO MULTA "
        "NA FATURA SEGUINTE A REALIZAÇÃO DO PAGAMENTO.")


def test_eq_mensagens_layout_2022_para_no_cabecalho_da_medicao():
    txt = ("ABR/2022 30/05/2022 R$******12.244,52\n"
           "PERÍODO DE REFERÊNCIA DA APURAÇÃO DOS INDICADORES DE CONTINUIDADE = 2/2022. VRC = R$ 2.356,82744\n"
           "Ocorreu uma movimentação de equipamento no dia 01/04/2022.\n"
           "Medidor Grandezas Postos Tarifários Leitura Anterior Leitura Atual Const. Medidor Consumo kWh/kW\n"
           "11638505-7 ENERGIA ATIVA - KWH PONTA 997038 022311 0,048000 1243,43\n")
    msg = equatorial.extrair_mensagens(txt)
    assert msg.startswith("PERÍODO DE REFERÊNCIA")
    assert msg.endswith("no dia 01/04/2022.")
    assert "Medidor" not in msg


def test_eq_mensagens_caixa_vazia_fica_nula():
    """FATURA Nº 81991941 (dez/2023): o total é seguido direto pelos tributos."""
    txt = "DEZ/2023 21/01/2024 R$******12.957,75\nPIS/PASEP 3047,34 0,9672% 29,47\n"
    assert equatorial.extrair_mensagens(txt) is None


def test_eq_assinatura_de_texto_embaralhado():
    embaralhado = "1 1 1 1 6 6 3 3 8 8 5 5 0 0 5 5 - - 7 7 E E N N E E R R G G I I A A"
    assert equatorial._RE_TEXTO_EMBARALHADO.search(embaralhado)
    normal = "11638505-7 ENERGIA ATIVA - KWH PONTA 997038 022311 0,048000 1243,43"
    assert not equatorial._RE_TEXTO_EMBARALHADO.search(normal)


# ── CHESP ────────────────────────────────────────────────────────────────────
def test_chesp_data_emissao_com_rotulo_quebrado():
    """FATURA Nº 1510617: 'DATA DE' numa linha, 'EMISSÃO: dd/mm/aaaa' na seguinte,
    com o CPF/CNPJ da outra coluna no meio."""
    txt = ("Rota: 825, Sequência: 155 80703340 NOTA FISCAL Nº 1510617 - SÉRIE 000 / DATA DE\n"
           "CPF/CNPJ: 02.292.266/0001-80 EMISSÃO: 16/01/2025\n")
    fat = chesp.extrair_fatura_chesp(txt, "FATURA Nº 1510617.pdf")
    assert fat["data_emissao"] == "2025-01-16"


def test_chesp_data_emissao_modelo6_quarta_coluna():
    txt = ("ANTERIOR ATUAL PRÓXIMA EMISSÃO APRESENTAÇÃO\n"
           "31/03/2022 30/04/2022 31/05/2022 30/04/2022 03/05/2022 DEMANDA CONTR.: 100\n")
    fat = chesp.extrair_fatura_chesp(txt, "FATURA Nº 119083.pdf")
    assert fat["data_emissao"] == "2022-04-30"
    assert fat["demanda_contratada_kw"] == 100.0


def test_chesp_demanda_rotulo_corrompido_pelo_ocr():
    """FATURA Nº 1830882 (escaneada): 'Demanda fora ponta-kW 100' virou
    'Danenda fm panesam 100'."""
    txt = "CUSTEIO DE ILUMINACAO PUBLICA MUNICIPAL 1 61,55000 61,55 Danenda fm panesam 100\n"
    fat = chesp.extrair_fatura_chesp(txt, "x.pdf")
    assert fat["demanda_contratada_kw"] == 100.0


def test_chesp_demanda_fallback_pelo_item_so_no_grupo_a():
    item = "DEMANDA kWw 100 28,57290 2.857,29 148,29 27,09000\n"
    fat_a = chesp.extrair_fatura_chesp("Classificação: A4 - Poder Público Tipo de\n" + item, "x.pdf")
    assert fat_a["demanda_contratada_kw"] == 100.0
    fat_b = chesp.extrair_fatura_chesp("Classificação: B3 - Poder Público Tipo de\n" + item, "x.pdf")
    assert fat_b["demanda_contratada_kw"] is None


def test_chesp_mensagens_entre_protocolo_e_itens():
    txt = ("01/2025 03/02/2025 R$895,96 Protocolo de autorização: 3522500001295227 - 16/01/2025 às 09:24:13\n"
           "Bandeira Tarifária Verde\n"
           "Itens de fatura Unid. Quant.\n")
    assert chesp.extrair_mensagens_chesp(txt) == "Bandeira Tarifária Verde"


def test_chesp_mensagens_modelo6_pela_linha_da_bandeira():
    txt = "Nº MEDIDOR: 171\nBandeira Tarifária Escassez Hídrica\nUNIDADE\n"
    assert chesp.extrair_mensagens_chesp(txt) == "Bandeira Tarifária Escassez Hídrica"


# ── aba validacao ────────────────────────────────────────────────────────────
def _lote():
    return {
        "fatura": pd.DataFrame({
            "id_fatura": ["EQUATORIAL_1", "EQUATORIAL_2", "CHESP_3"],
            "id_uc": ["111", "222", "333"],
            "competencia": ["2023-08", "2025-01", "2025-08"],
            "fornecedor": ["EQUATORIAL", "EQUATORIAL", "CHESP"],
            "classificacao_tarifaria": ["A A4 PODER PÚBLICO THS_VERDE", "B B3 CONVENCIONAL",
                                        "A4 - Poder Público"],
            "demanda_contratada_kw": [None, None, 0.0],
            "valor_total_r$": [100.0, 50.0, 30.0],
            "extraido_por_ocr": [False, False, True]}),
        "unidade_consumidora": pd.DataFrame({"id_uc": ["111", "222", "333"]}),
        "itens_fatura": pd.DataFrame({
            "id_fatura": ["EQUATORIAL_1", "EQUATORIAL_2", "CHESP_3", "CHESP_3"],
            "id_uc": ["111", "222", "333", "333"],
            "competencia": ["2023-08", "2025-01", "2025-08", "2025-08"],
            "item": ["CONSUMO", "CONSUMO", "CONSUMO S/ CONTRATO FP", "DEMANDA S/ CONTRATO P"],
            "valor_r$": [100.0, 45.0, 20.0, 10.0]}),
        "medicao": pd.DataFrame({
            "id_fatura": ["EQUATORIAL_1"] * 3 + ["CHESP_3"] * 9,
            "id_uc": ["111"] * 3 + ["333"] * 9,
            "competencia": ["2023-08"] * 3 + ["2025-08"] * 9,
            "Medidor": ["m1"] * 12}),
    }


def _regras(dfs, fid):
    v = dfs["validacao"]
    return set(v.loc[v["id_fatura"] == fid, "regra"])


def test_grupo_da_classificacao():
    g = derivados.grupo_da_classificacao
    assert g("A A4 PODER PÚBLICO - ESTADUAL THS_VERDE") == "A"
    assert g("A4 - Poder Público - Poder Público Estad") == "A"
    assert g("A OPT B3 PODER PÚBLICO - ESTADUAL") == "A"      # optante: continua AT
    assert g("B B3 PODER PÚBLICO - ESTADUAL CONVENCIONAL") == "B"
    assert g("B3 - Poder Público - Poder Público Estadual") == "B"
    assert g(None) is None and g("") is None


def test_validacao_regras_sem_mapa():
    dfs = _lote()
    derivados.aplicar(dfs)
    assert "validacao" in dfs
    assert "id_uc_canonico" not in dfs["validacao"].columns
    assert _regras(dfs, "EQUATORIAL_1") == {"DEMANDA_AUSENTE_GRUPO_A", "MEDICAO_INCOMPLETA"}
    assert _regras(dfs, "EQUATORIAL_2") == {"ITENS_NAO_FECHAM", "MEDICAO_VAZIA"}
    assert _regras(dfs, "CHESP_3") == {"DEMANDA_SEM_CONTRATO", "LIDA_POR_OCR"}
    assert list(dfs["validacao"]["gravidade"]).index("info") > \
        list(dfs["validacao"]["gravidade"]).index("erro")


def test_validacao_cruza_com_o_mapa_de_ucs(tmp_path):
    p = tmp_path / "mapa.json"
    p.write_text(json.dumps([
        {"id_uc": "111", "FORNECIMENTO (GRUPO AT/BT)": "TRIFÁSICO (BT)"},
        {"id_uc": "222", "FORNECIMENTO (GRUPO AT/BT)": "TRIFÁSICO (AT)"},
    ], ensure_ascii=False), encoding="utf-8")
    a = dicionario_uc.analisar_arquivo(str(p))
    regs, extras = dicionario_uc.aplicar_mapeamento(
        a, extras={"FORNECIMENTO (GRUPO AT/BT)": "fornecimento_grupo_at_bt"})
    dicionario_uc.salvar_mapa(regs, extras)
    dfs = _lote()
    derivados.aplicar(dfs)
    v = dfs["validacao"]
    assert "id_uc_canonico" in v.columns
    assert "GRUPO_DIVERGENTE_MAPA" in _regras(dfs, "EQUATORIAL_1")     # fatura A, mapa BT
    assert "DEMANDA_AUSENTE_UC_AT" in _regras(dfs, "EQUATORIAL_2")     # mapa AT, demanda vazia
    fora = v[v["regra"] == "UC_FORA_DO_MAPA"]
    assert list(fora["id_uc"]) == ["333"] and fora["id_fatura"].isna().all()


# ── mapa de UCs: chave e identificadores alternativos ───────────────────────
def test_mapa_ids_alternativos_e_linha_sem_chave(tmp_path):
    """Formato da planilha do TJGO: 'UC' (nova), 'id_uc' (formatada) e 'UC VELHA'
    em colunas separadas; uma linha só tem UC/UC VELHA (id_uc = '-')."""
    p = tmp_path / "d.json"
    p.write_text(json.dumps([
        {"UC": 274287601219, "id_uc": "2.742.876.012-19", "UC VELHA": 10008414082,
         "UNIDADE JUDICIÁRIA": "Juizado"},
        {"UC": 2260002025, "id_uc": "-", "UC VELHA": 2260002025,
         "UNIDADE JUDICIÁRIA": "Arquivo"},
    ]), encoding="utf-8")
    a = dicionario_uc.analisar_arquivo(str(p))
    assert a["chave"] == "id_uc" and a["chave_exata"]
    assert set(a["ids_extras_sugeridos"]) == {"UC", "UC VELHA"}
    assert a["sugeridos"] == {"unidade_institucional": "UNIDADE JUDICIÁRIA"}
    regs, _ = dicionario_uc.aplicar_mapeamento(
        a, mapeamento=a["sugeridos"], ids_extras=a["ids_extras_sugeridos"])
    dicionario_uc.salvar_mapa(regs, [])
    assert dicionario_uc.id_canonico("10008414082") == "274287601219"   # casa pela UC VELHA
    assert dicionario_uc.id_canonico("2.742.876.012-19") == "274287601219"
    assert dicionario_uc.id_canonico("2260002025") == "2260002025"       # linha sem id_uc
    assert dicionario_uc.campos_unidade_consumidora("2260002025")["unidade_institucional"] == "Arquivo"


def test_mapa_sem_id_uc_usa_o_campo_uc_como_chave(tmp_path):
    """JSON do painel: não tem 'id_uc'; a chave passa a ser 'UC'."""
    p = tmp_path / "j.json"
    p.write_text(json.dumps([{"UC": 5, "UC VELHA": 9, "OPERANTE": True}]), encoding="utf-8")
    a = dicionario_uc.analisar_arquivo(str(p))
    assert a["chave"] == "UC" and not a["chave_exata"]
    assert a["sugeridos"] == {"uc_operante": "OPERANTE"}
    regs, _ = dicionario_uc.aplicar_mapeamento(a, mapeamento=a["sugeridos"],
                                               ids_extras=["UC VELHA"])
    dicionario_uc.salvar_mapa(regs, [])
    assert dicionario_uc.id_canonico("9") == "5"
    assert dicionario_uc.campos_unidade_consumidora("5") == {"uc_operante": True}


def test_mapa_sem_nenhum_identificador_continua_erro(tmp_path):
    p = tmp_path / "x.json"
    p.write_text(json.dumps([{"codigo": "1"}]), encoding="utf-8")
    with pytest.raises(ValueError):
        dicionario_uc.analisar_arquivo(str(p))


# ── CLI ──────────────────────────────────────────────────────────────────────
def test_cli_infere_fornecedora_pelo_caminho():
    assert cli._inferir_fornecedor(r"C:\acervo\energia_tjgo\chesp\2022\FATURA.pdf") == "CHESP"
    assert cli._inferir_fornecedor(r"C:\acervo\equatorial\2023_a_2024\1.pdf") == "EQUATORIAL"
    assert cli._inferir_fornecedor(r"C:\pdfs\1.pdf") is None


def test_cli_listar_com_fornecedora_explicita(tmp_path):
    (tmp_path / "a.pdf").write_bytes(b"%PDF")
    lista = cli._listar(f"{tmp_path}=CHESP", subpastas=False)
    assert lista == [(str(tmp_path / "a.pdf"), "CHESP")]
    with pytest.raises(SystemExit):
        cli._listar(str(tmp_path), subpastas=False)      # sem fornecedora no caminho
