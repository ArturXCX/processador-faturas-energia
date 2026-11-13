"""Correções da conferência de água do TJGO (nov/2026): cada teste reproduz, com texto sintético modelado nas linhas reais,
um padrão que gerava erro/aviso na conferência — e o caso vizinho que NÃO pode mudar.

  * linha digitável de arrecadação (valor com dígitos verificadores) e sua ordem em página torta;
  * Saneago borderô por OCR: dígito verificador 0 lido como a letra O;
  * Saneago analítica por OCR: lançamentos sem o título, total conferido pelo histórico; hidrômetro vazio ("TIPO");
  * SANESC: 2ª via do autoatendimento (2021);
  * DEMAE Caldas Novas: "DEVOLUCAO NUMERÁRIO" impressa sem sinal;
  * DEMAE Panamá: valor só com apoio da linha digitável (o ano de uma data não vira valor);
  * SAAE Abadiânia: "CUSTO MINIMO FIXO", conta sem rótulos, OCR com competência = MÊS/FAT. e ano truncado no nome;
  * GSAN (SAE Catalão/Buriti): virada do hidrômetro e item lido sem vírgula pelo OCR;
  * SAAE Corumbá por OCR em pasta sem ano; SAAE Leopoldo de Bulhões fotografada.

Rodar:  PYTHONPATH=src python -m pytest tests/test_agua_conf_conferencia.py -q
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from faturas_app.core.agua import (demae, duam, gsan, leopoldo_bulhoes, saae_abadiania, saneago_analitica,  # noqa: E402
                                   saneago_bordero, sanesc)
from faturas_app.core.agua.base import (linha_digitavel, valor_linha_digitavel, vencimento_pelo_documento,  # noqa: E402
                                        vencimento_plausivel)


class DocFalso:
    def __init__(self, paginas, ocr=False, palavras=None):
        self.paginas = list(paginas)
        self.usou_ocr = ocr
        self.vazio = False
        self.paginas_ocr = [ocr] * len(self.paginas)
        self._palavras = palavras or []

    @property
    def texto(self):
        return "\f".join(self.paginas)

    @property
    def simples(self):
        return "\n".join(" ".join(l.split()) for p in self.paginas for l in p.splitlines())


# ── linha digitável ───────────────────────────────────────────────────────────
LINHA_DEMAE = "82660000000-2  94050311000-6 00000001002-5 88882505000-6"          # R$ 94,05
LINHA_ABAD = "82660000000.2       81450325000.7      12550521210.5      01627400002.1"   # R$ 81,45
LINHA_PANAMA = "82620000000-6 92960888023-3 38220250200-3 00001000000-8"         # R$ 92,96


def test_linha_digitavel_conferida_da_o_valor():
    assert valor_linha_digitavel("   " + LINHA_DEMAE) == 94.05
    assert valor_linha_digitavel(LINHA_ABAD) == 81.45
    assert linha_digitavel(LINHA_PANAMA)["conferida"] is True


def test_linha_digitavel_com_digito_trocado_e_reprovada():
    assert valor_linha_digitavel(LINHA_DEMAE.replace("94050311000-6", "94850311000-6")) is None    # valor adulterado
    assert valor_linha_digitavel(LINHA_DEMAE.replace("88882505000-6", "88882505001-6")) is None    # 4º bloco adulterado


def test_linha_digitavel_letra_o_do_ocr_vale_zero():
    assert valor_linha_digitavel("82620000001.4 O6100325000.0 12551123230.3 04533700002.5") == 106.10


def test_linha_digitavel_bloco_deslocado_para_a_linha_de_baixo_segue_a_coluna():
    """Página torta: o OCR põe o 2º bloco na linha seguinte. Lido na ordem do texto, o 3º bloco passaria por 2º (R$ 38,22)."""
    texto = ("     82620000000-6                 38220250200-3 00001000000-8\n"
             "                    92960888023-3\n")
    assert valor_linha_digitavel(texto) == 92.96


def test_linha_digitavel_incompleta_so_com_codigo_do_orgao():
    dois = "82650000000.3 93750325000.6 12551222220.4 0O5042400002.9"       # 4º bloco com 12 caracteres: linha incompleta
    assert valor_linha_digitavel(dois) is None
    assert valor_linha_digitavel(dois, orgao=("0325000",)) == 93.75
    assert valor_linha_digitavel(dois, orgao=("0888023",)) is None


# ── datas do nome do arquivo ──────────────────────────────────────────────────
def test_vencimento_com_ano_truncado_no_nome_usa_o_ano_da_competencia():
    assert vencimento_plausivel("2020-11-23", "2023-11") == "2023-11-23"
    assert vencimento_plausivel("2020-01-23", "2023-12") == "2024-01-23"
    assert vencimento_plausivel("2023-11-23", "2023-10") == "2023-11-23"       # plausível: não mexe
    assert vencimento_plausivel("2023-11-23", None) == "2023-11-23"


def test_vencimento_sem_ano_no_nome_vem_do_documento():
    caminho = os.path.join("agua", "saae_abadiania", "sem_", "FATURA DE ÁGUA N° 210021049 - VENC. 23.06.pdf")
    assert vencimento_pelo_documento("VENCIMENTO 23/06/2021   VALOR R$", caminho) == "2021-06-23"
    assert vencimento_pelo_documento("EMISSÃO 26/05/2021", caminho) is None


# ── Saneago borderô: DV 0 lido como letra O ───────────────────────────────────
def test_bordero_ocr_dv_zero_lido_como_letra_o():
    ln = "  1329041 O FORUM DE PORANGATU            RUA ADELINO AMERICO AZEVEDO QD. LT.          52     591,45"
    conta, dv, fim = saneago_bordero._linha_conta(ln, ocr=True)
    assert (conta, dv) == ("1329041", "0")
    assert ln[fim:].lstrip().startswith("FORUM DE PORANGATU")


def test_bordero_texto_nao_trata_letra_o_como_dv():
    ln = "  1329041 O FORUM DE PORANGATU            RUA ADELINO AMERICO AZEVEDO QD. LT.          52     591,45"
    assert saneago_bordero._linha_conta(ln)[:2] == ("132904", "1")              # PDF de texto: comportamento de sempre
    ok = "  1329041 0 FORUM DE PORANGATU            RUA ADELINO AMERICO AZEVEDO QD. LT.          52     591,45"
    assert saneago_bordero._linha_conta(ok, ocr=True)[:2] == ("1329041", "0")
    assert saneago_bordero._linha_conta(ok)[:2] == ("1329041", "0")


# ── Saneago analítica por OCR ─────────────────────────────────────────────────
_ANALITICA_OCR = """\
       SANEAMENTO DE GOIÁS S.A.                         FATURA ANALÍTICA DE ORGÃO PUBLICO
       ÓRGÃO PAGADOR:   2130 - TRIBUNAL DE JUSTICA             REFERÊNCIA:   07/2022
       ÓRGÃO AGRUPADOR:   2130 - TRIBUNAL DE JUSTICA
       CONTA   Nº:   1615070-8
       NOME:   FÓRUM DE CAMPINORTE
       ENDEREÇO:   AV. CENTRAL N.: Qd.: Lt: FORUM Bairro: NORTE Cidade: CAMPINORTE
       HIDRÔMETRO:   1-Medido
       B09S017967   TIPO DE CONSUMO:
       LEITURA   DATA   CONSUMO   27
       LEITURA ATUAL:   DATA   CONSUMO  ESTIMADO:   114
       CONSUMO  MÉDIO   18
       Descrição   Valor
       102 - TARIFA AGUA - COMERCIAL   303,83
       146 - CUSTO MINIMO FIXO - AGUA   14,64
       VALOR TOTAL (R$)   31847
       Fevereiro/2022   Março/2022   Abril/2022   Maio/2022   Junho/2022   Julho/2022   Média
       15   15   22   18   24   27   21
       176,99   176,99   259,52   212,36   283,10   318,47   237,91
       CONTA   Nº:   5181-0
       NOME:   TRIBUNAL DE JUSTIÇA DO ESTADO DE GO
       ENDEREÇO:   AV. 85 N.: 603 Bairro: SETOR SUL Cidade: GOIANIA
       HIDRÔMETRO:      TIPO DE CONSUMO:   2-Mínimo
       LEITURA   DATA   CONSUMO   10
       LEITURA ATUAL:   DATA   CONSUMO  ESTIMADO:   1
       Descrição   Valor
       138 - TARIFA MINIMA COMERCIAL   103,40
       224 - TARIFA MINIMA COLETA AFASTAMENTO ESGOTO COMER   82,70
       VALOR TOTAL (R$)   206,80
       Fevereiro/2022   Março/2022   Abril/2022   Maio/2022   Junho/2022   Julho/2022   Média
       10   10   10   10   10   10   10
       206,80   206,80   206,80   206,80   206,80   206,80   206,80
"""


def test_analitica_ocr_total_conferido_pela_soma_e_pelo_historico():
    res = saneago_analitica.extrair(DocFalso([_ANALITICA_OCR], ocr=True), "FATURA ANALÍTICA (5).pdf")
    f = res.faturas[0]
    assert f["conta"] == "16150708" and f["competencia"] == "2022-07"
    assert f["valor_total"] == 318.47 and f["soma_itens"] == 318.47           # "31847" lido sem a vírgula
    assert f["hidrometro"] == "B09S017967" and f["tipo_consumo"] == "1-Medido"
    assert [i["codigo"] for i in res.itens if i["id_fatura_agua"] == f["id_fatura_agua"]] == ["102", "146"]
    assert len([h for h in res.historico if h["id_fatura_agua"] == f["id_fatura_agua"]]) == 6


def test_analitica_ocr_itens_que_nao_fecham_nao_entram_e_tipo_nao_e_hidrometro():
    res = saneago_analitica.extrair(DocFalso([_ANALITICA_OCR], ocr=True), "FATURA ANALÍTICA (5).pdf")
    f = res.faturas[1]                       # itens somam 186,10 (um lançamento não foi lido), total impresso 206,80
    assert f["valor_total"] == 206.80 and f["soma_itens"] is None
    assert f["hidrometro"] is None           # campo vazio seguido de "TIPO DE CONSUMO"
    assert not [i for i in res.itens if i["id_fatura_agua"] == f["id_fatura_agua"]]


def test_analitica_ocr_conta_sem_o_traco_do_dv():
    """O OCR às vezes perde o traço ("CONTA Nº: 5402751" por 540275-1): o bloco tem de ser reconhecido (antes sumia)."""
    pagina = _ANALITICA_OCR.replace("CONTA   Nº:   5181-0", "CONTA   Nº:   51810")
    res = saneago_analitica.extrair(DocFalso([pagina], ocr=True), "FATURA ANALÍTICA (5).pdf")
    assert [(f["conta"], f["conta_formatada"]) for f in res.faturas] == [("16150708", "1615070-8"), ("51810", "5181-0")]
    so_texto = saneago_analitica.extrair(DocFalso([pagina], ocr=False), "FATURA ANALÍTICA.pdf")
    assert [f["conta"] for f in so_texto.faturas] == ["16150708"]              # PDF de texto: o traço continua obrigatório


def test_analitica_texto_segue_exigindo_o_titulo_lancamentos():
    """PDF de texto: sem o título LANÇAMENTOS não há leitura de itens nem correção de total (caminho do OCR não é usado)."""
    res = saneago_analitica.extrair(DocFalso([_ANALITICA_OCR], ocr=False), "FATURA ANALÍTICA.pdf")
    assert res.faturas[0]["valor_total"] == 318.0 and res.faturas[0]["soma_itens"] is None
    assert res.faturas[1]["hidrometro"] is None


# ── SANESC: 2ª via do autoatendimento ─────────────────────────────────────────
_SANESC_2VIA = """\
Atendimento  On-Line - Agência de Saneamento                           http://autoatendimento.exemplo/conta
                      SANESC
                      AV. DOM EMANUEL QD. 01 LT. 03                                               CONTA    DE   ÁGUA   E
                                                                   2° VIA DA CONTA
                      BAIRRO: BAIRRO DAS INDUSTRIA CEP:
                                                                     1234082021-2
                      75.250-000                                                                        ESGOTO
                                                                   05/10/2021 - 15:17
                      CNPJ : 00.000.000/0001-00
              TRIBUNAL   DE JUSTIÇA  DO ESTADO   DE GOIAS
              Endereço: RUA 10, 0 - CONJ TESTE - CEP: 75261-211 - S. CANEDO/GO                            MÊS/ANO
              Cod. ligação: 01234-5                                                                       08/2021
              Id. eletrônico: 0001234@15                                                        RES    COM      IND    PUB
                                                                                                 0       0       0       1
                                                DESCRIÇÃO                                                VALOR
                AGUA                                                                                               1 342,10
                DATA DE LEITURA    DATA LEITURA ORIG   DATA PROX LEITURA    VENCIMENTO               VALOR  A PAGAR
                   30/09/2021          30/09/2021              -             20/10/2021                R$1 342,10
                  L. ANTERIOR          L. ATUAL           CONS. REAL        CONS. FATURADO        MÉDIA         OCORRÊNCIA
                      2108               2286               178m3               178m3              23m3              34
                            HIDRÔMETRO                      VAZÃO              DIÂMETRO             DATA DA INSTALAÇÃO
                             X00X000000                      1,5m3               1/2"                    23/05/2019
                           VENCIMENTO                                                                VALOR  A PAGAR
                            20/10/2021                                                                 R$1 342,10
"""


def test_sanesc_segunda_via_do_autoatendimento():
    res = sanesc.extrair(DocFalso([_SANESC_2VIA]), os.path.join("2021", "FATURA AGOSTO.2021 - VCTO. 20.10.pdf"))
    f = res.faturas[0]
    assert f["id_fatura_agua"] == "SANESC_1234082021" and f["conta"] == "01234"
    assert f["competencia"] == "2021-08" and f["data_vencimento"] == "2021-10-20" and f["data_emissao"] == "2021-10-05"
    assert f["valor_total"] == 1342.10 and f["soma_itens"] == 1342.10
    assert (f["leitura_anterior"], f["leitura_atual"], f["consumo_m3"], f["consumo_faturado_m3"]) == (2108, 2286, 178, 178)
    assert f["hidrometro"] == "X00X000000" and f["categoria"] == "PUB"


# ── DEMAE Caldas Novas: devolução impressa sem sinal ──────────────────────────
def _itens_demae(*pares):
    f = {"fornecedor": "DEMAE_CALDAS_NOVAS"}
    from faturas_app.core.agua.base import novo_item
    return f, [novo_item(f, k, d, v) for k, (d, v) in enumerate(pares, 1)]


def test_demae_devolucao_vira_credito_quando_fecha_o_total():
    f, itens = _itens_demae(("FATURAMENTO AGUA", 59.18), ("DEVOLUCAO NUMERÁRIO Ref: 04/2025", 0.61), ("TAXA DE LIXO (05/2025)", 35.48))
    f["valor_total"] = 94.05
    demae._devolucao_como_credito(f, itens)
    assert itens[1]["valor"] == -0.61 and itens[1]["categoria_valor"] == "credito"
    assert round(sum(i["valor"] for i in itens), 2) == 94.05


def test_demae_devolucao_fica_como_esta_se_ja_fecha_ou_se_nao_resolve():
    f, itens = _itens_demae(("FATURAMENTO AGUA", 59.18), ("DEVOLUCAO NUMERÁRIO Ref: 04/2025", 0.61))
    f["valor_total"] = 59.79                         # já fecha com a devolução positiva
    demae._devolucao_como_credito(f, itens)
    assert itens[1]["valor"] == 0.61
    f["valor_total"] = 70.00                         # não fecha de jeito nenhum: não inventa
    demae._devolucao_como_credito(f, itens)
    assert itens[1]["valor"] == 0.61


# ── DEMAE Panamá ──────────────────────────────────────────────────────────────
def test_panama_valor_pela_linha_digitavel_e_nunca_pelo_ano_da_data():
    texto = ("DATA LEITURA ANTERIOR| DATA LEITURA ATUAL VENCIMENTO VALOR À PAGAR\n"
             "  09/02/2022     17/03/2022     05/04/2022\n"
             "VENCIMENTO - VALOR À PAGAR\n 05/04/2022\n")
    assert demae._valor_panama(texto) == (None, "")                     # antes saía R$ 20,22 (o ano de 05/04/2022)
    assert demae._valor_panama(texto + LINHA_PANAMA)[0] == 92.96


def test_panama_primeiro_e_segundo_blocos_com_codigo_do_orgao():
    assert demae._valor_panama("82640000000-4 27950888023-4")[0] == 27.95
    assert demae._valor_panama("82640000000-4 38220230300-2")[0] is None        # 3º bloco não passa por 2º


def test_panama_valor_impresso_confirmado_pelo_segundo_bloco():
    assert demae._valor_panama("TARIFA DE AGUA 235,98\n 82640)00002-0 35980888023-1 38220220900-5")[0] == 235.98
    assert demae._valor_panama("|R$ 6375\n 82640000000-4 G3750888023-3 0000 1000000")[0] == 63.75     # 1 caractere ilegível, recuperado pelo DV
    assert demae._valor_panama("1$ 3880\n 82690000000-9 .\n 3880088023 38220240100-8")[0] == 38.80     # um dígito a menos no código do órgão
    assert demae._valor_panama("TARIFA DE AGUA 36,45\n 30450888023-0")[0] is None                      # leitura do corpo que não confere


def test_panama_guia_de_2021_em_pasta_sem_ano():
    texto = ("PREFEITURA MUNICIPAL DE PANAMÁ\n Lançamento: 993588   Referência: 2021/05\n Pagamento até: 05/06/2021  Valor total:\n"
             " 82670000000 1 24360888202 9 10605010000 2 00000993588 3\n")
    res = demae.extrair(DocFalso([texto], ocr=True), os.path.join("agua", "demae_panama", "sem_", "FATURA N° 993588 - DEMAE PANAMÁ.pdf"), "DEMAE_PANAMA")
    f = res.faturas[0]
    assert f["id_fatura_agua"] == "DEMAE_PANAMA_993588"
    assert (f["competencia"], f["data_vencimento"], f["valor_total"]) == ("2021-05", "2021-06-05", 24.36)


# ── SAAE Abadiânia ────────────────────────────────────────────────────────────
_ABAD_TEXTO = """\
    INSCRIÇÃO                CLS    TAR                ECONOMIAS                NF / CONTA       EMISSÃO       MÊS / FAT.
   0001234.2                 PAR     C-1   RES    COM     IND    PUB    OUT     250023083        14/05/25          JUN/2025
               ULTIMOS     CONSUMOS                                              SERVIÇOS      E  TARIFAS
   MÊS FAT. CONS.  OCO    DC                                                 DESCRIÇÃO                        PREST.       VALOR
    JUN/25    5     000   030                            TARIFA DE AGUA (001 a 0010 - 11,290 * 005 m³ )                          56,45
                                                         TARIFA DE ESGOTO ( 50% )                                                41,35
    MAI/25    002   000   033
                                                         {extra}
                                                           HIDROMETRIA
   HIDRÔMETRO   INSTALAÇÃO    LEIT. ANT.  DT. LEITURA  LEIT. ATUAL DT. LEITURA   CONSUMO     DIAS/CONSUMO        OCO       LEITURISTA
   A00S000000   15/04/2003      5855     14/04/2025      5860      14/05/2025       5             030             000         013
    VENCIMENTO               23/06/2025                                                   VALOR    R$                      {total}
    INSCRIÇÃO                  MÊS FAT:                   NF / CONTA                 VENCIMENTO               VALOR
      0001234.2                 JUN/2025                   250023083                            23/06/2025        {total}
"""


def test_abadiania_custo_minimo_fixo_entra_quando_os_itens_nao_fecham():
    pagina = _ABAD_TEXTO.format(extra="CUSTO MINIMO FIXO                                                       12,50", total="110,30")
    res = saae_abadiania.extrair(DocFalso([pagina]), "FATURA Nº 250023083 - SAAE ABADIÂNIA - MAIO.2025 - VENC. 23.06.2025.pdf")
    f = res.faturas[0]
    assert f["valor_total"] == 110.30 and f["soma_itens"] == 110.30
    assert [i["descricao"] for i in res.itens][-1] == "CUSTO MINIMO FIXO"


def test_abadiania_fatura_que_ja_fecha_nao_muda():
    pagina = _ABAD_TEXTO.format(extra="", total="97,80")
    res = saae_abadiania.extrair(DocFalso([pagina]), "FATURA Nº 250023083 - SAAE ABADIÂNIA - MAIO.2025 - VENC. 23.06.2025.pdf")
    assert res.faturas[0]["soma_itens"] == 97.80
    assert [i["codigo"] for i in res.itens] == ["030", None]             # leitura de sempre (inclusive o código herdado da coluna DC)


_ABAD_SEM_ROTULOS = """\
        CNPJ:   00.000.000/0001-00                  Insc. Est. : ISENTO
        0001234.2       PAR   200  C-1   001  01/01/00    210016274    30/04/2021   MAI/2021
       FORUM  DE ABADIANIA
        A00S000000      15/04/2003     001  TARIFA DE AGUA(0000 a 0010 - 5,43 *            54,30
                                       002  TARIFA DE ESGOTO (50%)                         27,15
                                23/05/2021                                    81,45
      0001234.2   FORUM  DE ABADIANIA                                           MAI/2021
                                23/05/2021                                    81,45
                                 0001234.05.21.210016274
         82660000000.2       81450325000.7      12550521210.5      01627400002.1
"""


def test_abadiania_conta_impressa_sem_rotulos():
    res = saae_abadiania.extrair(DocFalso([_ABAD_SEM_ROTULOS]), os.path.join("sem_", "FATURA DE ÁGUA.pdf"))
    f = res.faturas[0]
    assert f["id_fatura_agua"] == "SAAE_ABADIANIA_210016274" and f["conta"] == "00012342"
    assert (f["competencia"], f["data_vencimento"], f["valor_total"], f["soma_itens"]) == ("2021-05", "2021-05-23", 81.45, 81.45)


def test_abadiania_ocr_competencia_e_o_mes_do_vencimento_e_o_valor_vem_da_linha_digitavel():
    texto = ("NOV/23 TARIFA DE AGUA (000 0010 6,840 * 010 mº ) 68,40\n"
             "OUT/2023 em 19/09/23 3,50\n"
             " 0001255.11.23.230045337\n"
             " 82620000001.4 O6100325000.0 12551123230.3 04533700002.5\n")
    caminho = os.path.join("2023", "FATURA Nº 230045337 - SAAE ABADIÂNIA - OUTUBRO.2023 - VENC. 23.11.20.pdf")
    f = saae_abadiania.extrair(DocFalso([texto], ocr=True), caminho).faturas[0]
    assert f["numero_fatura"] == "230045337"
    assert f["competencia"] == "2023-11"                # MÊS/FAT. impresso (o nome do arquivo diz OUTUBRO)
    assert f["data_vencimento"] == "2023-11-23"         # o nome traz "23.11.20" (ano truncado)
    assert f["valor_total"] == 106.10                   # antes saía 3,50 (a 2ª via ao lado de uma data)


def test_abadiania_ocr_itens_parciais_nao_viram_total():
    texto = "01 | AGUA(O0O A 0010 -5430*10) 54,30\n"       # o esgoto não foi lido: 54,30 não é o total
    f = saae_abadiania.extrair(DocFalso([texto], ocr=True), os.path.join("2021", "FATURA DE ÁGUA - venc. 23.08.pdf")).faturas[0]
    assert f["valor_total"] is None and f["competencia"] == "2021-08"
    texto += "4 ) 02 |TARIFADE ESGOTO (50,0%) 27,15\n"      # água + esgoto a 50 %: aí sim
    f = saae_abadiania.extrair(DocFalso([texto], ocr=True), os.path.join("2021", "FATURA DE ÁGUA - venc. 23.08.pdf")).faturas[0]
    assert f["valor_total"] == 81.45 and f["soma_itens"] == 81.45


# ── GSAN: virada do hidrômetro e item sem vírgula no OCR ──────────────────────
_GSAN = """\
                                                                                                Vencimento                        Valor   a Pagar    (R$)
                                                                                                 18/07/2026                              {total}
           TRIBUNAL  DE JUSTICA  DO ESTADO   DE GOIAS
            RES      COM      PÚB      IND     TOTAL
            0000     0000     0001    0000      0001                                FATURA     N.º   11104052        HIDRÔMETRO       N.º     Y00H000000
             DADOS   DE  FATURAMENTO                                            DESCRIÇÃO     DOS   ITENS  FATURADOS                           Valor (R$)
           Mês/Ano  Faturamento:  06/2026                                        FATURAMENTO       AGUA   - 1.577,42
                                        Data           Leitura                   > Pública-Normal                                    113         1.577,42
                   Leitura Atual:    12/06/2026          {atual}                      {esgoto}
                 Leitura Anterior:   13/05/2026         9903                     > Pública-Normal                                                1.261,93
              Consumo  Faturado:  {faturado}
                                                                                TOTAL   A PAGAR                                                  {total}
                      FATURA:  06/2026 Nº 11104052    VENCIMENTO:    18/07/2026                        VALOR   (R$): {total}
                                                                       MATRÍCULA:   11723    DÍGITO:  4
"""


def _gsan(atual="16", faturado="113", esgoto="FATURAMENTO       ESGOTO    - 1.261,93", total="2.839,35", ocr=False):
    pagina = _GSAN.format(atual=atual, faturado=faturado, esgoto=esgoto, total=total)
    return gsan.extrair(DocFalso([pagina], ocr=ocr), "FATURA Nº 11104052 - SAE CATALÃO - JUNHO.2026 - VENC. 18.07.2026.pdf", "SAE_CATALAO")


def test_gsan_virada_do_hidrometro_nao_da_consumo_negativo():
    f = _gsan().faturas[0]
    assert (f["leitura_anterior"], f["leitura_atual"]) == (9903, 16)
    assert f["consumo_m3"] == 113 and f["consumo_faturado_m3"] == 113        # antes: −9887
    assert "virou" in f["observacao"]


def test_gsan_leitura_normal_segue_sendo_a_diferenca_das_leituras():
    f = _gsan(atual="10016").faturas[0]
    assert f["consumo_m3"] == 113 and not f.get("observacao")


def test_gsan_troca_de_hidrometro_usa_o_faturado():
    f = _gsan(atual="40", faturado="55").faturas[0]
    assert f["consumo_m3"] == 55


def test_gsan_ocr_item_lido_sem_virgula_entra_pelo_detalhe():
    res = _gsan(esgoto="FATURAMENTO       ESGOTO     1.261 93", ocr=True)
    assert res.faturas[0]["soma_itens"] == 2839.35
    assert [i["descricao"] for i in res.itens] == ["FATURAMENTO AGUA", "FATURAMENTO ESGOTO"]
    so_texto = _gsan(esgoto="FATURAMENTO       ESGOTO     1.261 93", ocr=False)      # PDF de texto: nada muda
    assert so_texto.faturas[0]["soma_itens"] == 1577.42


# ── SAAE Corumbá (DUAM) por OCR, em pasta sem ano ─────────────────────────────
def test_corumba_ocr_competencia_do_documento_e_vencimento_pelo_nome():
    texto = ("FORUM DE CORUMBA DE GOIAS\n MES/ANO:04/2021\n DESCRICAO VALOR\n"
             "  TARIFA  DE AGUA                                              51,22\n"
             "  TARIFA  BASICO OPERACIONAL                                    6,00\n")
    caminho = os.path.join("agua", "saae_corumba", "sem_", "FATURA DE ÁGUA - VENC. 27.05.pdf")
    f = duam.extrair(DocFalso([texto], ocr=True), caminho, "SAAE_CORUMBA").faturas[0]
    assert f["competencia"] == "2021-04" and f["data_vencimento"] == "2021-05-27" and f["valor_total"] == 57.22


def test_corumba_ocr_total_impresso_vale_mais_que_a_soma_de_itens_lidos_pela_metade():
    """O OCR põe o valor da água na linha de cima e o extrator casava "TARIFA DE AGUA" com o 6,00 da linha de baixo: a guia
    de R$ 287,61 saía com R$ 12,00. O total impresso ("… À PAGAR" / "R$287,61") manda; itens que não fecham não entram."""
    texto = ("FORUM DE CORUMBA DE GOIAS   MES/ANO:07/2021\n DESCRICÃO  VALOR\n ee  281,61\n TARIFA DE  AGUA\n"
             " TARIFA  BASICO OPERACIONAL  6,00\n DATA LEITURA ANTERIOR DATA LEITURA ATÁL  UQLGR À PAGAR\n"
             " 25/06/2021  |  26/07/2021  |  27/08/2021  ] R$287,61\n")
    caminho = os.path.join("agua", "saae_corumba", "sem_", "FATURA DE ÁGUA Nº 593283 - SAAE CORUMBÁ - venc. 27.08.pdf")
    res = duam.extrair(DocFalso([texto], ocr=True), caminho, "SAAE_CORUMBA")
    f = res.faturas[0]
    assert (f["competencia"], f["data_vencimento"], f["valor_total"], f["soma_itens"]) == ("2021-07", "2021-08-27", 287.61, None)
    assert not res.itens


def test_corumba_ocr_com_mes_no_nome_do_arquivo_continua_valendo_o_nome():
    texto = "FORUM DE CORUMBA DE GOIAS\n MES/ANO:04/2021\n  TARIFA  DE AGUA                51,22\n"
    caminho = os.path.join("agua", "saae_corumba", "2021", "FATURA SAAE CORUMBÁ - 08-2021 - Venc. 27.09.pdf")
    f = duam.extrair(DocFalso([texto], ocr=True), caminho, "SAAE_CORUMBA").faturas[0]
    assert f["competencia"] == "2021-08"


# ── SAAE Leopoldo de Bulhões fotografada ──────────────────────────────────────
def _palavras(linhas):
    """Palavras posicionais no formato do OCR (x0, y0, x1, y1, texto, bloco, linha, palavra), uma linha do Tesseract por item."""
    ws = []
    for n, ln in enumerate(linhas, 1):
        for k, t in enumerate(ln.split()):
            ws.append((10.0 + 40 * k, 20.0 * n, 45.0 + 40 * k, 20.0 * n + 10, t, 1, n, k + 1))
    return ws


def _leopoldo(total_layout, linhas_ocr):
    # layout em colunas de uma foto torta: descrição e valor desencontrados, total com dígito trocado (ou ausente)
    pagina = ("CÓD. LIG.: 01851-5 MAPA CAD.: A-4-00070\n                 DESCRIÇÃO           VALOR\n AGUA      1.275,62\n TARIFA DE      14,34\n"
              f" Data da leitura anterior  Data da leitura  Vencimento  Valor à pagar\n 11/08/2024  12/09/2024  20/10/2024  R$ {total_layout}\n"
              if total_layout else "CÓD. LIG.: 01851-5\n TARIFA DE\n AGUA\n")
    doc = DocFalso([pagina], ocr=True, palavras=[_palavras(linhas_ocr)])
    return leopoldo_bulhoes.extrair(doc, "FATURA Nº 018510820246 - SAAE LEOPOLDO DE BULHÕES - AGOSTO.2024 - VENC. 20.10.2024.pdf")


def test_leopoldo_ocr_total_com_um_digito_trocado_vale_a_soma_dos_itens():
    res = _leopoldo("2.889,96", ["TARIFA DE AGUA 1.275,62", "CUSTO MINIMO FIXO 14,34", "11/08/2024 12/09/2024 20/10/2024 R$ 1.288,96"])
    f = res.faturas[0]
    assert f["valor_total"] == 1289.96 and f["soma_itens"] == 1289.96
    assert [i["descricao"] for i in res.itens] == ["TARIFA DE AGUA", "CUSTO MINIMO FIXO"]


def test_leopoldo_ocr_sem_total_no_layout_usa_itens_que_fecham_com_o_valor_impresso():
    res = _leopoldo(None, ["TARIFA DE AÁGUA 110,50", "CUSTO MIBUNAL MINIMO DE JUSTICA FIXO DO ESTADO DE GO w 14,34", "12/12/2024 Diâmetro R$ Data instalação 124,84"])
    assert res.faturas[0]["valor_total"] == 124.84


def test_leopoldo_ocr_total_lido_sem_itens_ganha_itens_so_se_somarem_o_total():
    pagina = (" Data da leitura anterior  Data da leitura  Vencimento  Valor à pagar\n 13/06/2024  12/07/2024  19/09/2024  R$ 63,79\n")
    linhas = ["TARIFA DE AGUA 49,45", "CUSTO MINIMO FIXO 14,34", "19/09/2024 R$ 63,79"]
    res = leopoldo_bulhoes.extrair(DocFalso([pagina], ocr=True, palavras=[_palavras(linhas)]), "FATURA Nº 018510720248 - JULHO.2024 - VENC. 19.09.2024.pdf")
    assert res.faturas[0]["valor_total"] == 63.79 and res.faturas[0]["soma_itens"] == 63.79
    linhas[0] = "TARIFA DE AGUA 48,45"                 # um item lido errado: os itens não entram e o total não muda
    res = leopoldo_bulhoes.extrair(DocFalso([pagina], ocr=True, palavras=[_palavras(linhas)]), "FATURA Nº 018510720248 - JULHO.2024 - VENC. 19.09.2024.pdf")
    assert res.faturas[0]["valor_total"] == 63.79 and res.faturas[0]["soma_itens"] is None and not res.itens


def test_abadiania_consumo_impresso_como_asteriscos():
    pagina = _ABAD_TEXTO.format(extra="", total="97,80").replace("5855     14/04/2025      5860      14/05/2025       5  ", "5921     15/06/2026      5921      14/07/2026      ***")
    f = saae_abadiania.extrair(DocFalso([pagina]), "FATURA Nº 260034459 - SAAE ABADIÂNIA - JULHO.2026 - VENC. 23.08.2026.pdf").faturas[0]
    assert (f["hidrometro"], f["leitura_anterior"], f["leitura_atual"], f["consumo_m3"], f["dias"]) == ("A00S000000", 5921, 5921, 0, 30)


def test_leopoldo_ocr_sem_confirmacao_nao_inventa_total():
    res = _leopoldo(None, ["TARIFA DE AGUA 110,50", "CUSTO MINIMO FIXO 14,34", "12/12/2024 R$ 999,99"])
    assert res.faturas[0]["valor_total"] is None
