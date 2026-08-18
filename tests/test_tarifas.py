"""
Testes da aba 'tarifas' (derivados._derivar_tarifas).

A aba é uma tabela de REFERÊNCIA: 1 linha por (fornecedor, item,
tarifa_unitaria_r$), na competência em que a combinação apareceu pela primeira
vez. Bandeira tarifária e linhas sem tarifa ficam de fora.

`test_dedup_e_deterministico` é o que primeiro pega a regressão se alguém
remover o `kind="mergesort"` do sort: sem sort estável o desempate entre linhas
de mesma competência muda entre execuções.

Rodar:  PYTHONPATH=src python -m pytest tests/ -q
"""
import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from faturas_app.core import derivados, schema  # noqa: E402


def _dfs(itens, faturas=None):
    """Monta {'fatura', 'itens_fatura'} a partir de listas de dicts."""
    faturas = faturas or [{"id_fatura": "EQUATORIAL_1", "fornecedor": "EQUATORIAL",
                           "id_uc": "1", "competencia": "2024-01"}]
    itf = pd.DataFrame(itens)
    for col in ("tipo", "unidade", "preco_unitario_com_tributos_r$", "item_normalizado"):
        if col not in itf.columns:
            itf[col] = ("FORNECIMENTO" if col == "tipo"
                        else "kWh" if col == "unidade"
                        else itf["item"] if col == "item_normalizado" else 1.0)
    return {"fatura": pd.DataFrame(faturas), "itens_fatura": itf}


def _tarifas(dfs):
    derivados._derivar_tarifas(dfs)
    return dfs["tarifas"]


def test_colunas_de_saida_na_ordem_do_schema():
    t = _tarifas(_dfs([{"id_fatura": "EQUATORIAL_1", "competencia": "2024-01",
                        "item": "CONSUMO", "tarifa_unitaria_r$": 0.5}]))
    assert list(t.columns) == schema.all_canonical("tarifas")
    assert list(t.columns)[0] == "fornecedor"


def test_remove_bandeira_tarifaria():
    """Item com 'BAND' sai; o resto fica."""
    t = _tarifas(_dfs([
        {"id_fatura": "EQUATORIAL_1", "competencia": "2024-01",
         "item": "ADC BANDEIRA VERMELHA", "tarifa_unitaria_r$": 0.02},
        {"id_fatura": "EQUATORIAL_1", "competencia": "2024-01",
         "item": "CONSUMO", "tarifa_unitaria_r$": 0.5},
    ]))
    assert list(t["item"]) == ["CONSUMO"]


def test_remove_bandeira_em_qualquer_grafia():
    """'BAND' é casado sem diferenciar maiúsculas e no meio do nome."""
    t = _tarifas(_dfs([
        {"id_fatura": "EQUATORIAL_1", "competencia": "2024-01",
         "item": "DEV. DIF. BAND TARIFÁRIA", "tarifa_unitaria_r$": 0.01},
        {"id_fatura": "EQUATORIAL_1", "competencia": "2024-01",
         "item": "Bandeira Tarifaria Escassez", "tarifa_unitaria_r$": 0.03},
        {"id_fatura": "EQUATORIAL_1", "competencia": "2024-01",
         "item": "DEMANDA", "tarifa_unitaria_r$": 18.92},
    ]))
    assert list(t["item"]) == ["DEMANDA"]


def test_remove_tarifa_vazia():
    """Item financeiro (sem tarifa) não aparece, mesmo estando em itens_fatura."""
    t = _tarifas(_dfs([
        {"id_fatura": "EQUATORIAL_1", "competencia": "2024-01",
         "item": "PARCELAMENTO", "tipo": "ITENS FINANCEIROS",
         "tarifa_unitaria_r$": None},
        {"id_fatura": "EQUATORIAL_1", "competencia": "2024-01",
         "item": "CONSUMO", "tarifa_unitaria_r$": 0.5},
    ]))
    assert list(t["item"]) == ["CONSUMO"]


def test_dedup_mantem_a_competencia_mais_antiga():
    """Mesmo fornecedor+item+tarifa, fora de ordem na entrada: sobra a mais antiga."""
    t = _tarifas(_dfs(
        [{"id_fatura": "EQUATORIAL_1", "competencia": "2024-01",
          "item": "CONSUMO", "tarifa_unitaria_r$": 0.5},
         {"id_fatura": "EQUATORIAL_2", "competencia": "2023-06",
          "item": "CONSUMO", "tarifa_unitaria_r$": 0.5}],
        faturas=[{"id_fatura": "EQUATORIAL_1", "fornecedor": "EQUATORIAL",
                  "id_uc": "1", "competencia": "2024-01"},
                 {"id_fatura": "EQUATORIAL_2", "fornecedor": "EQUATORIAL",
                  "id_uc": "1", "competencia": "2023-06"}]))
    assert len(t) == 1
    assert t["competencia"].iat[0] == "2023-06"


def test_tarifa_diferente_do_mesmo_item_gera_linhas_separadas():
    """A aba é uma linha do tempo: cada tarifa nova do item vira uma linha."""
    t = _tarifas(_dfs(
        [{"id_fatura": "EQUATORIAL_1", "competencia": "2023-06",
          "item": "CONSUMO", "tarifa_unitaria_r$": 0.45},
         {"id_fatura": "EQUATORIAL_2", "competencia": "2024-01",
          "item": "CONSUMO", "tarifa_unitaria_r$": 0.50}],
        faturas=[{"id_fatura": "EQUATORIAL_1", "fornecedor": "EQUATORIAL",
                  "id_uc": "1", "competencia": "2023-06"},
                 {"id_fatura": "EQUATORIAL_2", "fornecedor": "EQUATORIAL",
                  "id_uc": "1", "competencia": "2024-01"}]))
    assert len(t) == 2
    assert sorted(t["tarifa_unitaria_r$"]) == [0.45, 0.50]


def test_fornecedor_separa_distribuidoras_com_tarifa_coincidente():
    """
    CHESP e Equatorial chegam a coincidir no valor da tarifa de DEMANDA em
    dezembro. As duas precisam aparecer, cada uma com seu fornecedor — nunca
    fundidas numa linha só.
    """
    t = _tarifas(_dfs(
        [{"id_fatura": "EQUATORIAL_1", "competencia": "2023-12",
          "item": "DEMANDA", "tarifa_unitaria_r$": 18.92},
         {"id_fatura": "CHESP_1", "competencia": "2023-12",
          "item": "DEMANDA", "tarifa_unitaria_r$": 18.92}],
        faturas=[{"id_fatura": "EQUATORIAL_1", "fornecedor": "EQUATORIAL",
                  "id_uc": "1", "competencia": "2023-12"},
                 {"id_fatura": "CHESP_1", "fornecedor": "CHESP",
                  "id_uc": "2", "competencia": "2023-12"}]))
    assert len(t) == 2
    assert sorted(t["fornecedor"]) == ["CHESP", "EQUATORIAL"]


def _lote_empatado(n=120):
    """n linhas do mesmo (fornecedor, item, tarifa) e da MESMA competência —
    todas empatadas no critério de ordenação, distinguíveis só pelo preço."""
    itens = [{"id_fatura": f"EQUATORIAL_{i}", "competencia": "2022-01",
              "item": "CONSUMO", "tarifa_unitaria_r$": 0.5,
              "preco_unitario_com_tributos_r$": float(i)}
             for i in range(1, n + 1)]
    faturas = [{"id_fatura": f"EQUATORIAL_{i}", "fornecedor": "EQUATORIAL",
                "id_uc": str(i), "competencia": "2022-01"} for i in range(1, n + 1)]
    return itens, faturas


def test_dedup_e_deterministico():
    """
    Trava a PROPRIEDADE que o kind='mergesort' garante: com muitas linhas
    empatadas na competência, a que sobrevive é sempre a PRIMEIRA na ordem de
    entrada. O desempate em si é arbitrário, mas precisa ser sempre o mesmo (a
    ordem original de itens_fatura).

    Nota honesta sobre o alcance deste teste: no pandas/numpy desta venv,
    trocar 'mergesort' por 'quicksort' NÃO o faz falhar — o introsort do numpy
    acaba preservando a ordem nos casos testados. Ou seja, ele não prova hoje
    que o mergesort é necessário. O mergesort continua sendo a escolha certa
    por ser o único que garante estabilidade POR CONTRATO, em vez de depender
    de um detalhe de implementação que pode mudar de versão; e este teste é o
    que vai pegar a regressão se essa garantia deixar de valer.
    """
    itens, faturas = _lote_empatado()
    for semente in (None, 0, 1, 2, 3):
        entrada = itens if semente is None else (
            pd.DataFrame(itens).sample(frac=1, random_state=semente).to_dict("records"))
        t = _tarifas(_dfs(entrada, faturas))
        assert len(t) == 1
        esperado = entrada[0]["preco_unitario_com_tributos_r$"]
        assert t["preco_unitario_com_tributos_r$"].iat[0] == esperado, (
            f"sobreviveu a linha errada com a semente {semente} — sort instável?")


def test_mesmo_lote_duas_vezes_da_resultado_identico():
    """Reprodutibilidade: mesma entrada, mesmo resultado, execução após execução."""
    itens, faturas = _lote_empatado()
    primeira = _tarifas(_dfs(itens, faturas))
    for _ in range(5):
        assert _tarifas(_dfs(itens, faturas)).equals(primeira)


def test_rodar_duas_vezes_da_o_mesmo_resultado():
    """Idempotência: recalcular sobre o mesmo dfs não muda nada."""
    dfs = _dfs([{"id_fatura": "EQUATORIAL_1", "competencia": "2024-01",
                 "item": "CONSUMO", "tarifa_unitaria_r$": 0.5}])
    primeira = _tarifas(dfs).copy()
    segunda = _tarifas(dfs)
    assert segunda.equals(primeira)


def test_sem_itens_devolve_aba_vazia_com_as_colunas():
    """Aba vazia ainda precisa ter o cabeçalho certo (formato estável)."""
    dfs = {"fatura": pd.DataFrame(), "itens_fatura": pd.DataFrame()}
    t = _tarifas(dfs)
    assert t.empty
    assert list(t.columns) == schema.all_canonical("tarifas")


def test_itens_sem_coluna_esperada_nao_derruba():
    """Planilha antiga sem 'tarifa_unitaria_r$': devolve vazio, não explode."""
    dfs = {"fatura": pd.DataFrame([{"id_fatura": "EQUATORIAL_1",
                                    "fornecedor": "EQUATORIAL"}]),
           "itens_fatura": pd.DataFrame([{"id_fatura": "EQUATORIAL_1",
                                          "item": "CONSUMO"}])}
    t = _tarifas(dfs)
    assert t.empty
    assert list(t.columns) == schema.all_canonical("tarifas")


def test_aba_entra_no_calculo_completo_e_na_ordem_de_saida():
    """_calcular instala 'tarifas'; SHEET_ORDER a coloca depois de itens_fatura."""
    dfs = _dfs([{"id_fatura": "EQUATORIAL_1", "competencia": "2024-01",
                 "item": "CONSUMO", "tarifa_unitaria_r$": 0.5}])
    dfs["fatura"]["id_uc"] = "1"
    derivados._calcular(dfs)
    assert "tarifas" in dfs
    assert len(dfs["tarifas"]) == 1
    ordem = schema.SHEET_ORDER
    assert ordem.index("tarifas") == ordem.index("itens_fatura") + 1


def test_concat_cria_a_aba_mesmo_sem_ela_na_planilha_enviada():
    """
    Planilha gerada por versão anterior do app (sem a aba 'tarifas'): a
    concatenação precisa criar a aba do zero, não ignorá-la.
    """
    res_dfs = _dfs([{"id_fatura": "EQUATORIAL_1", "competencia": "2024-01",
                     "item": "CONSUMO", "tarifa_unitaria_r$": 0.5}])
    res_dfs["fatura"]["id_uc"] = "1"
    res_dfs["itens_fatura"]["id_uc"] = "1"
    assert "tarifas" not in res_dfs
    derivados.aplicar_concat(res_dfs, None)
    assert "tarifas" in res_dfs
    assert list(res_dfs["tarifas"]["item"]) == ["CONSUMO"]


def test_concat_com_a_aba_ja_existente_recalcula_sem_erro_de_tamanho():
    """
    Segunda concatenação: a planilha enviada JÁ tem 'tarifas', com um número de
    linhas diferente do recalculado. A aba é substituída inteira — não pode
    tentar escrever coluna a coluna numa aba de outro tamanho.
    """
    res_dfs = _dfs([{"id_fatura": "EQUATORIAL_1", "competencia": "2024-01",
                     "item": "CONSUMO", "tarifa_unitaria_r$": 0.5}])
    res_dfs["fatura"]["id_uc"] = "1"
    res_dfs["itens_fatura"]["id_uc"] = "1"
    # aba "antiga" com 3 linhas que não correspondem ao recálculo (1 linha)
    res_dfs["tarifas"] = pd.DataFrame({
        c: ["x", "y", "z"] for c in schema.all_canonical("tarifas")})
    derivados.aplicar_concat(res_dfs, None)
    assert len(res_dfs["tarifas"]) == 1
    assert list(res_dfs["tarifas"]["item"]) == ["CONSUMO"]


def test_concat_registra_a_aba_nos_metadados():
    """Sem entrada no meta, o próximo upload cairia no casamento por similaridade."""
    res_dfs = _dfs([{"id_fatura": "EQUATORIAL_1", "competencia": "2024-01",
                     "item": "CONSUMO", "tarifa_unitaria_r$": 0.5}])
    res_dfs["fatura"]["id_uc"] = "1"
    res_dfs["itens_fatura"]["id_uc"] = "1"
    meta = {"abas": {}}
    derivados.aplicar_concat(res_dfs, meta)
    cols = [c["canonico"] for c in meta["abas"]["tarifas"]["colunas"]]
    assert cols == schema.all_canonical("tarifas")


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
