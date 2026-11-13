"""valor_irpj / valor_bruto nas faturas de água (T5). Textos sintéticos; nenhum PDF real.

Rodar:  PYTHONPATH=src python -m pytest tests/test_agua_irpj.py -q
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from faturas_app.core.agua import base, controller_agua, gsan, schema_agua as S  # noqa: E402


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


def _fatura(itens_spec, **extra):
    """Monta uma fatura sintética e a fecha; itens_spec = [(descricao, valor_str)]."""
    f = base.nova_fatura("BURITI_ALEGRE_AMBIENTAL", "FATURA Nº 185278 - X.pdf")
    f["conta_formatada"] = "1382537-2"
    f["competencia"] = "01/2025"
    f.update(extra)
    itens = [base.novo_item(f, i, d, v) for i, (d, v) in enumerate(itens_spec, 1)]
    base.fechar_fatura(f, itens, "FATURA Nº 185278 - X.pdf")
    return f


def test_fatura_com_irpj_buriti():
    res = gsan.extrair(DocFalso([_GSAN]), "FATURA Nº 110495 - BURITI ALEGRE AMBIENTAL - JANEIRO.2024 - VENC. 05.02.2024.pdf",
                       "BURITI_ALEGRE_AMBIENTAL")
    f = res.faturas[0]
    assert f["valor_total"] == 382.03
    assert f["valor_taxas"] == 9.12            # continua incluindo o IRPJ (-19,26 + 28,38)
    assert f["valor_irpj"] == -19.26
    assert f["valor_bruto"] == 401.29


def test_fechar_fatura_somas_com_irpj():
    f = _fatura([("TARIFA AGUA", "288,20"), ("FATURAMENTO ESGOTO", "288,20"),
                 ("IRPJ - (4,80%)", "-29,08"), ("TARIFA BÁSICA (01/2025)", "29,50")])
    assert f["valor_irpj"] == -29.08
    assert f["valor_bruto"] == 605.9
    assert f["valor_taxas"] == 0.42
    assert f["valor_total"] == 576.82


def test_fatura_sem_irpj():
    f = _fatura([("TARIFA AGUA", "100,00"), ("FATURAMENTO ESGOTO", "80,00"), ("TARIFA BÁSICA (01/2025)", "10,00")])
    assert f["valor_irpj"] is None
    assert f["valor_total"] == 190.0
    assert f["valor_bruto"] == f["valor_total"]


def test_dois_itens_de_irpj_somam():
    f = _fatura([("TARIFA AGUA", "200,00"), ("IRPJ - (4,80%)", "-10,00"), ("IRPJ - COMPLEMENTO", "-2,50")])
    assert f["valor_irpj"] == -12.5
    assert f["valor_total"] == 187.5
    assert f["valor_bruto"] == 200.0


def test_sem_valor_total_nem_itens():
    f = _fatura([])
    assert f["valor_total"] is None
    assert f["valor_irpj"] is None
    assert f["valor_bruto"] is None


def test_valor_total_impresso_prevalece():
    f = _fatura([("TARIFA AGUA", "200,00"), ("IRPJ - (4,80%)", "-9,60")], valor_total="382,03")
    assert f["valor_total"] == 382.03
    assert f["valor_irpj"] == -9.6
    assert f["valor_bruto"] == 391.63


def test_esquema_posicao_e_numericas():
    cols = S.FATURA_COLS
    assert cols.index("valor_irpj") == cols.index("valor_multa_juros") + 1
    assert cols.index("valor_bruto") == cols.index("valor_irpj") + 1
    assert cols.index("valor_bruto") < cols.index("valor_total")
    assert "valor_irpj" in S.COLUNAS_NUMERICAS[S.ABA_FATURAS] and "valor_bruto" in S.COLUNAS_NUMERICAS[S.ABA_FATURAS]
    assert "valor_irpj" in S.linha_vazia(S.ABA_FATURAS) and "valor_bruto" in S.linha_vazia(S.ABA_FATURAS)

    f = _fatura([("TARIFA AGUA", "200,00"), ("IRPJ - (4,80%)", "-9,60")])
    res = base.Resultado(faturas=[f])
    df = controller_agua.dataframes(res, [], incluir_mapa=False)[S.ABA_FATURAS]
    assert list(df.columns) == S.FATURA_COLS
    assert str(df["valor_irpj"].dtype).startswith("float") and str(df["valor_bruto"].dtype).startswith("float")
    assert df["valor_irpj"].iloc[0] == -9.6 and df["valor_bruto"].iloc[0] == 200.0


def test_borderos_nao_ganham_colunas():
    for cols in (S.BORDERO_COLS, S.CONTA_BORDERO_COLS):
        assert "valor_irpj" not in cols and "valor_bruto" not in cols
