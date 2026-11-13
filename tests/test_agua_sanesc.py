"""SANESC (Senador Canedo) — medição (dias, leituras, consumo) e categoria nos três modelos de conta 2022+.

Os PDFs reais não estão no repositório: cada teste usa o texto em layout de uma página sintética, modelada nas
linhas reais (cadastro, hidrômetro e código de baixa anonimizados; colunas, leituras, consumos e valores mantidos).

Rodar:  PYTHONPATH=src python -m pytest tests/test_agua_sanesc.py -q
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from faturas_app.core.agua import sanesc  # noqa: E402


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


_TOPO = """\
                  AGENCIA       DE  SANEAMENTO           DE   SENADOR       CANEDO       - GO
                  SANESC   - GO CNPJ:  00000000000000
                             2ª Via   - Fatura    de   Serviços,     Água     e Esgoto
     Cadastro                 Código de Baixa     Hidrômetro            Referência            Vencimento
           000001234            2-000000-1-8        X00X000000              {ref}             {venc}
      Proprietário                                          Compromissário/Inquilino
      000001234                                             CLIENTE    DE   TESTE
"""

_CAB_MEDICAO = "     Nº Economia Dias Proxima Leitura Corte      Data Leitura Leitura Anterior Leitura Atual Resid. Consumo Cons. Fat\n"

_RODAPE = """\
         Tabela de Qualidade da Água - Data 01/05/2025
      Parâmetros Resultados Padrão     Unidade
      Cloro          0,80      0,2-5,0    mg/L
                                                     TOTAL  DA  CONTA:                               {total}
"""


def _pagina_dez2025() -> str:
    """Modelo novo (dez/2025): próxima leitura = '0'; categoria no fim da linha seguinte ao cabeçalho."""
    return (_TOPO.format(ref="12/2025", venc="27/02/2026") + _CAB_MEDICAO
            + "         1       27         0                     12/02/2026      6437        6512               75       75\n"
            + "       Referên Consumo  Leitura  Nº Dias   Data    Categoria                    Ocorrência\n"
            + "       11/2025 68        6437      36    15/01/2026 PUBLICO                     LEITURA    NORMAL\n"
            + "       10/2025 53        6369      29    10/12/2025\n"
            + "        9/2025 86        6316      32    10/11/2025                   Discriminação das Receitas\n"
            + "        8/2025 138       6230      33    08/10/2025\n"
            + "        7/2025 161       6092      31    04/09/2025 AGUA                                           708,48\n"
            + "        6/2025 219       5931      31    04/08/2025\n"
            + "        5/2025 122       5712      28    04/07/2025 ESGOTO                                         566,78\n"
            + _RODAPE.format(total="1.275,26"))


def _pagina_2022(ref, venc, prox, data_leitura, ant, atual, cons, dias, agua) -> str:
    """Modelo 2022: próxima leitura = DATA, depois a data da leitura; 'Categoria / Ocorrência' em linhas separadas."""
    return (_TOPO.format(ref=ref, venc=venc) + _CAB_MEDICAO
            + f"         1        {dias}                  {prox}   {data_leitura}       {ant}        {atual}                {cons}        {cons}\n"
            + "      Categoria                                      Ocorrência\n"
            + "      PUBLICO                                        LEITURA    NORMAL\n"
            + "        Refer  Consumo   Leitura  Nº Dias   Data                        Discriminação das Receitas\n"
            + "        2/2022  47        2550      30     23/03/2022\n"
            + f"        1/2022  36        2503      30     18/02/2022 AGUA                                            {agua}\n"
            + _RODAPE.format(total=agua))


def _pagina_ago2025(linha_medicao=None) -> str:
    """Modelo ago/2025: próxima leitura em branco."""
    medicao = linha_medicao or "         1       33                               08/10/2025       6092        6230               138      138"
    return (_TOPO.format(ref="8/2025", venc="31/10/2025") + _CAB_MEDICAO + medicao + "\n"
            + "      Categoria                                     Ocorrência\n"
            + "      PUBLICO                                        LEITURA   NORMAL\n"
            + "       Refer  Consumo    Leitura  Nº Dias  Data                        Discriminação das Receitas\n"
            + "       7/2025 161        6092     31     04/09/2025\n"
            + "       6/2025 219        5931     31     04/08/2025 AGUA                                          1.314,54\n"
            + "       5/2025 122        5712     28     04/07/2025 ESGOTO                                        1.051,63\n"
            + _RODAPE.format(total="2.366,17"))


def _extrair(pagina: str, nome: str):
    res = sanesc.extrair(DocFalso([pagina]), nome)
    assert len(res.faturas) == 1
    return res.faturas[0]


def _medicao(f):
    return (f["dias"], f["data_leitura_atual"], f["leitura_anterior"], f["leitura_atual"], f["consumo_m3"], f["consumo_faturado_m3"])


def test_dez2025_proxima_leitura_zero_e_categoria_no_fim_da_linha():
    f = _extrair(_pagina_dez2025(), "FATURA - SANESC - DEZEMBRO.2025 - VENC. 27.02.2026.pdf")
    assert _medicao(f) == (27, "2026-02-12", 6437, 6512, 75, 75)
    assert f["categoria"] == "PUBLICO"
    assert f["tipo_consumo"] == "LEITURA NORMAL"
    assert f["valor_total"] == 1275.26


def test_jul2022_proxima_leitura_e_data():
    pag = _pagina_2022("7/2022", "25/09/2022", "26/09/2022", "25/08/2022", 2804, 2876, 72, 30, "650,36")
    f = _extrair(pag, "FATURA - SANESC - JULHO.2022 - VENC. 25.09.2022.pdf")
    assert _medicao(f) == (30, "2022-08-25", 2804, 2876, 72, 72)   # a data que vale é a 2ª ("Data Leitura"), não a "Próxima Leitura Corte"
    assert f["categoria"] == "PUBLICO"
    assert f["tipo_consumo"] == "LEITURA NORMAL"
    assert f["valor_total"] == 650.36


def test_mar2022_proxima_leitura_e_data():
    pag = _pagina_2022("3/2022", "30/05/2022", "26/05/2022", "27/04/2022", 2550, 2607, 57, 30, "423,55")
    f = _extrair(pag, "FATURA - SANESC - MARÇO.2022 - VENC. 30.05.2022.pdf")
    assert _medicao(f) == (30, "2022-04-27", 2550, 2607, 57, 57)
    assert f["categoria"] == "PUBLICO"
    assert f["valor_total"] == 423.55


def test_ago2025_proxima_leitura_em_branco_continua_funcionando():
    f = _extrair(_pagina_ago2025(), "FATURA - SANESC - AGOSTO.2025 - VENC. 31.10.2025.pdf")
    assert _medicao(f) == (33, "2025-10-08", 6092, 6230, 138, 138)
    assert f["categoria"] == "PUBLICO"
    assert f["tipo_consumo"] == "LEITURA NORMAL"
    assert f["valor_total"] == 2366.17


def test_linha_de_medicao_com_texto_extra_no_fim_nao_casa():
    """A regex continua ancorada: lixo depois do consumo faturado não pode virar medição."""
    pag = _pagina_ago2025("         1       33                               08/10/2025       6092        6230               138      138  OBS")
    f = _extrair(pag, "FATURA - SANESC - AGOSTO.2025 - VENC. 31.10.2025.pdf")
    assert f["leitura_anterior"] is None and f["leitura_atual"] is None
    assert f["dias"] is None and f["data_leitura_atual"] is None


def test_ramo_antigo_ml2_continua_funcionando():
    """Sem a linha completa de medição, o ramo antigo lê 'cons.fat consumo leitura dias' (ex.: '72 72 2876 2')."""
    pag = _TOPO.format(ref="7/2022", venc="25/09/2022") + "       72   72   2876   2\n" + _RODAPE.format(total="650,36")
    f = _extrair(pag, "FATURA - SANESC - JULHO.2022 - VENC. 25.09.2022.pdf")
    assert (f["consumo_faturado_m3"], f["consumo_m3"], f["leitura_atual"]) == (72, 72, 2876)
