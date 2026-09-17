"""Extração de faturas de ÁGUA (todas as concessionárias no mesmo modelo).

Os PDFs reais não estão no repositório: os testes usam o texto em layout (o que `texto.Documento` produz) de páginas
sintéticas modeladas nos documentos reais do acervo (borderô Saneago 2024, fatura GSAN/Buriti Alegre 2024).

Rodar:  PYTHONPATH=src python -m pytest tests/test_agua.py -q
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from faturas_app.core import atualizacao  # noqa: E402
from faturas_app.core.agua import (base, controller_agua, derivados_agua, gsan, identificar, saneago_bordero,  # noqa: E402
                                   schema_agua as S, texto)


class DocFalso:
    def __init__(self, paginas, ocr=False):
        self.paginas = list(paginas)
        self.usou_ocr = ocr
        self.vazio = False

    @property
    def texto(self):
        return "\f".join(self.paginas)

    @property
    def simples(self):
        return "\n".join(" ".join(l.split()) for p in self.paginas for l in p.splitlines())


def _pos(*partes):
    """Monta uma linha colocando cada texto numa coluna: (coluna, texto) alinha à esquerda; (coluna, texto, 'd') alinha o
    FIM do texto na coluna."""
    buf = ""
    for p in partes:
        col, txt = p[0], p[1]
        if len(p) > 2 and p[2] == "d":
            col = col - len(txt)
        if col > len(buf):
            buf += " " * (col - len(buf))
        else:
            buf += " "
        buf += txt
    return buf


# ── utilidades de texto ───────────────────────────────────────────────────────
def test_moeda_competencia_data():
    assert texto.moeda("1.254,06") == 1254.06
    assert texto.moeda("R$ 340,2") == 340.2
    assert texto.moeda("-19,26") == -19.26
    assert texto.moeda("85") == 85.0
    assert texto.competencia("04/2024") == "2024-04"
    assert texto.competencia("MAR/2021") == "2021-03"
    assert texto.competencia("Janeiro/2026") == "2026-01"
    assert texto.data_iso("30/05/2024") == "2024-05-30"
    assert texto.data_iso("2024-05-30") == "2024-05-30"        # já em ISO: não inverte dia/ano
    assert texto.data_iso("14/01/24") == "2024-01-14"
    assert texto.competencia_do_nome("FATURA Nº 110495 - BURITI - JANEIRO.2024 - VENC. 05.02.2024.pdf") == "2024-01"


def test_categoria_valor():
    cv = texto.categoria_valor
    assert cv("TARIFA AGUA") == "agua"
    assert cv("SERV. DE CAPTACAO E DIST. AGUA") == "agua"
    assert cv("CUSTO MINIMO FIXO - ESGOTO") == "esgoto"
    assert cv("COLETA/AFASTAMENTO ESGOTO PUBLICA") == "esgoto"
    assert cv("TARIFA BÁSICA (01/2024)") == "taxas"
    assert cv("IRPJ - (4,80%)") == "taxas"
    assert cv("TAXA DE LIXO (01/2024)") == "taxas"
    assert cv("PREFEITURA - TAXA RESIDUOS SOLIDOS") == "taxas"
    assert cv("ATUALIZ. MONETARIA PART AGUA") == "multa_juros"
    assert cv("MULTA POR PAGAMENTO EM ATRASO") == "multa_juros"


def test_texto_ilegivel():
    assert texto.texto_ilegivel("      \n   \n")
    assert texto.texto_ilegivel("!\"#$%&'()*+,-./ 0123 MTPIUVDWKMPIKXDYQMGFDT $9:;<=> 5 & 7 #A@C")
    assert not texto.texto_ilegivel("FATURA DE ÁGUA — CONSUMO 23 m3 — VALOR TOTAL 382,03 — VENCIMENTO 05/02/2024 " * 3)


def test_layout_coloca_palavras_em_colunas():
    palavras = [(10, 10, 40, 20, "CONTA"), (200, 10, 240, 20, "VALOR"), (10, 30, 60, 40, "1627885"), (200, 30, 240, 40, "1.254,06")]
    t = texto.layout(palavras)
    l1, l2 = t.splitlines()
    assert l1.strip().startswith("CONTA") and l1.rstrip().endswith("VALOR")
    assert l2.strip().startswith("1627885") and l2.rstrip().endswith("1.254,06")
    assert abs(l1.index("VALOR") - l2.index("1.254,06")) <= 2


# ── identificação ─────────────────────────────────────────────────────────────
def test_identificar_por_cnpj_e_tipo():
    assert identificar.fornecedor("CNPJ: 43.390.208/0001-77 Vencimento Valor a Pagar", "x.pdf") == "BURITI_ALEGRE_AMBIENTAL"
    assert identificar.fornecedor("CNPJ : 01.616.929/0001-02 SANEAMENTO DE GOIÁS", "x.pdf") == "SANEAGO"
    assert identificar.fornecedor("nada", "FATURA Nº 1 - SAAE CORUMBÁ - JANEIRO.pdf", "") == "SAAE_CORUMBA"
    assert identificar.tipo("SANEAGO Nº FATURA: 3000483958 NOME DO ÓRGÃO AGRUPADOR: CONTA - DV", "SANEAGO") == identificar.TIPO_BORDERO
    assert identificar.tipo("SANEAMENTO DE GOIÁS FATURA ANALÍTICA DE ÓRGÃO PÚBLICO", "SANEAGO") == identificar.TIPO_ANALITICA
    assert identificar.tipo("DEMAE Matrícula: 21628-3", "DEMAE_CALDAS_NOVAS") == identificar.TIPO_FATURA


# ── base ──────────────────────────────────────────────────────────────────────
def test_rx_tolera_espacamento_e_numero_do_nome():
    assert base.rx(r"QUANTIDADE DE CONTAS").search("QUANTIDADE    DE CONTAS   AGRUPADAS:")
    assert base.numero_do_nome("FATURA Nº 110495 - BURITI ALEGRE AMBIENTAL - JANEIRO.2024.pdf") == "110495"
    assert base.numero_do_nome("FATURA - N° 1002916 - DEMAE PANAMÁ.pdf") == "1002916"
    assert base.numero_do_nome("11723-4.pdf") is None


def test_categoria_por_contagem_respeita_ordem_do_cabecalho():
    assert base.categoria_por_contagem("  RES   COM   PÚB   IND   TOTAL\n  000   000   002   000   002\n") == "PUB"
    assert base.categoria_por_contagem("  RES  COM  IND  PÚB\n  000  000  000  001\n") == "PUB"
    assert base.categoria_por_contagem("RES. COM. IND. PUB. OUT\n 1 0 0 0 0\n") == "RES"


def test_fechar_fatura_soma_categorias_e_prefere_numero_do_nome_no_ocr():
    f = base.nova_fatura("BURITI_ALEGRE_AMBIENTAL", "FATURA Nº 185278 - X.pdf", ocr=True)
    f["numero_fatura"] = "1852978"          # OCR trocou um dígito
    f["conta_formatada"] = "1382537-2"
    f["competencia"] = "01/2025"
    f["data_vencimento"] = "24/02/2025"
    itens = [base.novo_item(f, 1, "TARIFA AGUA", "288,20"), base.novo_item(f, 2, "FATURAMENTO ESGOTO", "288,20"),
             base.novo_item(f, 3, "IRPJ - (4,80%)", "-29,08"), base.novo_item(f, 4, "TARIFA BÁSICA (01/2025)", "29,50")]
    base.fechar_fatura(f, itens, "FATURA Nº 185278 - X.pdf")
    assert f["numero_fatura"] == "185278"
    assert f["id_fatura_agua"] == "BURITI_ALEGRE_AMBIENTAL_185278"
    assert f["conta"] == "13825372" and f["competencia"] == "2025-01" and f["data_vencimento"] == "2025-02-24"
    assert f["valor_agua"] == 288.20 and f["valor_esgoto"] == 288.20 and f["valor_taxas"] == 0.42
    assert f["soma_itens"] == 576.82 and f["valor_total"] == 576.82


# ── borderô Saneago (página sintética no layout real de 2024) ─────────────────
def _pagina_bordero():
    L = [
        "   SANEAMENTO        DE  GOIÁS S.A.",
        "   Nº  FATURA:    3000483958            MÊS/ANO     REF:   04/2024",
        "   DATA    DE  EMISSÃO:     14/05/2024          VENCIMENTO:       30/05/2024",
        "   NOME DO ÓRGÃO AGRUPADOR:",
        "   TRIBUNAL DE JUSTICA ESTADO DE GOIÁS                                                    2130  2130",
        _pos((118, "VALOR R$"), (133, "VALOR R$"), (148, "VALOR R$")),
        _pos((3, "CONTA  - DV"), (16, "NOME   CLIENTE"), (53, "LOGRADOURO"), (100, "CONSUMO   (M³)"), (118, "ÁGUA"), (132, "ESGOTO"), (147, "SMRSU")),
        _pos((3, "1627885 2"), (15, "TRIBUNAL DE JUSTIÇA DO ESTADO DE GO"), (53, "RUA OTTO CARMO DE MORAES, 179 QD. 63-D"),
             (104, "112", "d"), (124, "1.254,06", "d"), (138, "1.050,84", "d")),
        _pos((3, "1584740 3"), (15, "FORUM DE ALEXANIA"), (53, "AV. BRIGADEIRO EDUARDO GOMES, 256"),
             (104, "33", "d"), (124, "375,35", "d"), (152, "45,00", "d")),
        _pos((3, "CONSUMO    FATURADO    TOTAL   / VALOR  TOTAL  DA  FATURA"), (104, "145", "d"), (124, "1.629,41", "d"),
             (138, "1.050,84", "d"), (152, "45,00", "d")),
        "   RETENÇÕES     DE IMPOSTOS",
        "   IRPJ                                                   ALÍQUOTA    TOTAL         BASE   DE CALCULO",
        "   4,80%                                                        4,80%                   2.680,25",
        _pos((3, "CONSUMO    FATURADO    TOTAL   / VALOR  TOTAL  DA  FATURA"), (104, "145", "d"), (140, "R$   2.725,25", "d")),
        "   QUANTIDADE    DE CONTAS   AGRUPADAS:   2",
        "   VALOR  DO  IMPOSTO   RETIDO  (água e esgoto)                                        R$   128,65",
        "   VALOR  FINAL  DA FATURA                                                             R$   2.596,60",
        "   COMUNICADO PARA PAGAMENTO   Nº FATURA 3000483958   MÊS/ANO REF. 04/2024",
        "   VALOR  TOTAL  EM R$   2.596,60",
    ]
    return "\n".join(L)


def test_bordero_saneago_formato_novo():
    res = saneago_bordero.extrair(DocFalso([_pagina_bordero()]), "FATURAS DE ÁGUA - SANEAGO - ABRIL.2024.pdf")
    assert len(res.borderos) == 1 and len(res.contas_bordero) == 2
    b = res.borderos[0]
    assert b["id_bordero_agua"] == "SANEAGO_3000483958" and b["competencia"] == "2024-04"
    assert b["data_emissao"] == "2024-05-14" and b["data_vencimento"] == "2024-05-30"
    assert b["formato"] == "novo" and b["quantidade_contas"] == 2 and b["quantidade_contas_extraidas"] == 2
    assert b["valor_agua"] == 1629.41 and b["valor_esgoto"] == 1050.84 and b["valor_smrsu"] == 45.0
    assert b["base_calculo"] == 2680.25 and b["aliquota_irpj"] == 4.8 and b["valor_retido"] == 128.65
    assert b["valor_final"] == 2596.60 and b["bate_total"] == "SIM" and b["escaneado"] == "NÃO"
    assert b["cod_pagador"] == "2130" and b["nome_agrupador"] == "TRIBUNAL DE JUSTICA ESTADO DE GOIÁS"
    c1, c2 = res.contas_bordero
    assert c1["conta"] == "16278852" and c1["conta_formatada"] == "1627885 2"
    assert c1["nome_cliente"] == "TRIBUNAL DE JUSTIÇA DO ESTADO DE GO"
    assert c1["logradouro"].startswith("RUA OTTO CARMO DE MORAES")
    assert c1["consumo_m3"] == 112 and c1["valor_agua"] == 1254.06 and c1["valor_esgoto"] == 1050.84 and c1["valor_smrsu"] is None
    assert c1["valor_total"] == 2304.90
    # coluna ESGOTO em branco não desloca o SMRSU
    assert c2["valor_agua"] == 375.35 and c2["valor_esgoto"] is None and c2["valor_smrsu"] == 45.0 and c2["consumo_m3"] == 33


def test_bordero_linha_escorregada_e_centavos_sem_zero():
    """Logradouro longo empurra os números para a esquerda dos rótulos (formato antigo: consumo/valor água, consumo/valor esgoto)
    e a Saneago imprime centavos sem o zero (',03' = 0,03): nada pode ser perdido."""
    cab = _pos((3, "CONTA - DV"), (16, "NOME CLIENTE"), (53, "LOGRADOURO"), (103, "ÁGUA"), (110, "VALOR R$"), (126, "ESGOTO"), (133, "VALOR R$"))
    cols = saneago_bordero._colunas(cab, _pos((100, "CONSUMO (M³)"), (123, "CONSUMO (M³)")))
    ln = "        1989327 2 TRIBUNAL DE JUSTIÇA DO ESTADO DE GO AV. PRESIDENTE VARGAS QD. 72 LT. 1/8 JARDIM BOA ESPERANCA APARECIDA DE G 10 91,40 360 3.710,40"
    valores, consumos, ini = saneago_bordero._numeros_da_cauda(ln, cols, False)
    assert valores == {"agua": 91.40, "esgoto": 3710.40} and consumos == {"consumo": 10, "consumo_esgoto": 360}
    assert ln[ini:].strip().startswith("10 91,40")
    cab2 = _pos((3, "CONTA  - DV"), (16, "NOME   CLIENTE"), (53, "LOGRADOURO"), (100, "CONSUMO   (M³)"), (118, "ÁGUA"), (132, "ESGOTO"), (147, "SMRSU"))
    cols2 = saneago_bordero._colunas(cab2, "")
    ln2 = _pos((3, "1555004 4"), (15, "FORUM DE CIDADE OCIDENTAL"), (53, "RUA 11A QD. LT. MORADA DAS GARCAS"), (104, "125", "d"),
               (124, "1.488,47", "d"), (138, ",03", "d"), (152, "25,50", "d"))
    valores2, consumos2, _ = saneago_bordero._numeros_da_cauda(ln2, cols2, False)
    assert valores2 == {"agua": 1488.47, "esgoto": 0.03, "smrsu": 25.50} and consumos2 == {"consumo": 125}


def test_bordero_conta_com_dv_colado_no_ocr():
    pag = _pagina_bordero().replace("1627885 2 ", "16278852 —")
    res = saneago_bordero.extrair(DocFalso([pag], ocr=True), "x.pdf")
    assert res.contas_bordero[0]["conta"] == "16278852"
    assert res.borderos[0]["escaneado"] == "SIM" and "OCR" in res.borderos[0]["observacao"]


# ── fatura GSAN (Buriti Alegre 2024) ──────────────────────────────────────────
_GSAN = """
                                                 CNPJ: 43.390.208/0001-77                     Vencimento                      Valor   a Pagar   (R$)
                                           Rua DOM  EMANUEL,  SN QD. 66 LT. 13                 05/02/2024                             382,03
                                                                                          Matrícula      Dígito                       Grupo
                                                                                           1382537            2                         74
          TRIBUNAL  DE JUSTIÇA  DO ESTADO  DE  GOIÁS
                                                                                                  www.buritialegreambiental.com.br
          R. MACIEL, SN
          CALADIA
          BURITI ALEGRE  - GO CEP: 75660-000
           CADASTRO DO CLIENTE
            RES     COM      PÚB      IND    TOTAL
            000      000     002      000      002                               FATURA     N.º   110495         HIDRÔMETRO        N.º    Y17N318694
            DADOS    DE FATURAMENTO                                           DESCRIÇÃO    DOS   ITENS  FATURADOS                          Valor (R$)
           Mês/Ano Faturamento:  01/2024
                                                                               TARIFA  AGUA   - 207,17
                   Leitura Atual:   12/01/2024        3250                     > Pública                                        23 m3          207,17
                Leitura Anterior:   13/12/2023        3227                     FATURAMENTO      ESGOTO    - 165,74
             Consumo  Faturado:  23                                            IRPJ - IMPOSTO DE RENDA PESSOA JURÍDICA               -19,26
             Dias de Consumo: 30                                               TARIFA BÁSICA (01/2024)                                28,38
             Ocorrência do Mês: Lido                                           TOTAL A PAGAR                                          382,03
                                                                               PIS (1,65%)     6,29
              HISTÓRICO DE CONSUMO
           Mês      Tipo    Leitura  Lido Faturado
           07/2023  Lido     3031     39     39
           08/2023  Lido     3070     39     39
           FATURAS PENDENTES
                         FATURA:  01/2024 Nº 110495      VENCIMENTO:  05/02/2024                           VALOR (R$): 382,03
                         NOME:  TRIBUNAL DE JUSTIÇA DO ESTADO DE GOIÁS                                      AUTENTICAÇÂO  NO VERSO
                         MATRÍCULA:  1382537                              DÍGITO: 2
"""


def test_fatura_gsan_buriti():
    res = gsan.extrair(DocFalso([_GSAN]), "FATURA Nº 110495 - BURITI ALEGRE AMBIENTAL - JANEIRO.2024 - VENC. 05.02.2024.pdf", "BURITI_ALEGRE_AMBIENTAL")
    assert len(res.faturas) == 1
    f = res.faturas[0]
    assert f["id_fatura_agua"] == "BURITI_ALEGRE_AMBIENTAL_110495"
    assert f["conta"] == "13825372" and f["competencia"] == "2024-01" and f["data_vencimento"] == "2024-02-05"
    assert f["valor_total"] == 382.03 and f["soma_itens"] == 382.03
    assert f["valor_agua"] == 207.17 and f["valor_esgoto"] == 165.74 and f["valor_taxas"] == 9.12
    assert f["leitura_anterior"] == 3227 and f["leitura_atual"] == 3250 and f["consumo_m3"] == 23 and f["dias"] == 30
    assert f["hidrometro"] == "Y17N318694" and f["categoria"] == "PUB" and f["tipo_consumo"] == "Lido"
    assert f["nome_cliente"] == "TRIBUNAL DE JUSTIÇA DO ESTADO DE GOIÁS"
    assert f["logradouro"] == "R. MACIEL, SN CALADIA BURITI ALEGRE - GO CEP: 75660-000"
    assert [i["descricao"] for i in res.itens] == ["TARIFA AGUA", "FATURAMENTO ESGOTO", "IRPJ - IMPOSTO DE RENDA PESSOA JURÍDICA", "TARIFA BÁSICA (01/2024)"]
    assert [h["competencia"] for h in res.historico] == ["2023-07", "2023-08"]


# ── derivados / validação / planilha ──────────────────────────────────────────
def _lote_sintetico():
    res_b = saneago_bordero.extrair(DocFalso([_pagina_bordero()]), "bordero.pdf")
    res_f = gsan.extrair(DocFalso([_GSAN]), "FATURA Nº 110495.pdf", "BURITI_ALEGRE_AMBIENTAL")
    res_b.estender(res_f)
    return res_b


def test_validacao_regras_basicas():
    res = _lote_sintetico()
    f = res.faturas[0]
    f["soma_itens"] = 300.0                      # força ITENS_NAO_FECHAM
    val = derivados_agua.aplicar(res, duplicados=[("BURITI_ALEGRE_AMBIENTAL_110495", "copia.pdf")])
    regras = {v["regra"] for v in val}
    assert "ITENS_NAO_FECHAM" in regras and "DUPLICIDADE" in regras
    assert "BORDERO_NAO_CONFERE" not in regras
    assert f["conta_canonica"] == "13825372"
    assert res.contas_bordero[0]["conta_canonica"] == "16278852"


def test_cruzamento_bordero_analitica():
    res = _lote_sintetico()
    a = base.nova_fatura("SANEAGO", "analitica.pdf", origem="analitica")
    a.update(conta="16278852", conta_formatada="1627885-2", competencia="2024-04", valor_total=2300.00)
    base.fechar_fatura(a, [], "")
    res.faturas.append(a)
    val = derivados_agua.cruzar_bordero_analitica(res)
    regras = sorted(v["regra"] for v in val)
    assert regras == ["ANALITICA_DIVERGE_BORDERO", "CONTA_SEM_ANALITICA"]


def test_dataframes_planilha_e_concatenacao(tmp_path):
    res = _lote_sintetico()
    val = derivados_agua.aplicar(res)
    dfs = controller_agua.dataframes(res, val, incluir_mapa=False)
    assert list(dfs[S.ABA_FATURAS].columns) == S.FATURA_COLS
    assert len(dfs[S.ABA_BORDEROS]) == 1 and len(dfs[S.ABA_CONTAS_BORDERO]) == 2 and len(dfs[S.ABA_FATURAS]) == 1
    caminho = tmp_path / "agua.xlsx"
    controller_agua.escrever_planilha(dfs, str(caminho))
    lido = controller_agua.ler_planilha(str(caminho))
    assert S.ABA_FATURAS in lido and "glossario" in lido
    assert controller_agua.divergencias(lido) == []
    comb, resumo = controller_agua.concatenar(lido, dfs)
    assert len(comb[S.ABA_FATURAS]) == 1 and len(comb[S.ABA_BORDEROS]) == 1      # dedup por id
    assert any("duplicata" in r for r in resumo)


# ── atualização obrigatória ───────────────────────────────────────────────────
def test_versao_mais_nova():
    assert atualizacao.mais_nova("v4.0", "3.1.0")
    assert atualizacao.mais_nova("V.4.0.1", "4.0.0")
    assert not atualizacao.mais_nova("V.3.1.0", "4.0.0")
    assert not atualizacao.mais_nova("4.0", "4.0.0")
    assert not atualizacao.mais_nova("", "4.0.0")


def test_verificar_desligado_por_variavel(monkeypatch):
    monkeypatch.setenv("FATURAS_SEM_ATUALIZACAO", "1")
    assert atualizacao.verificar() is None
