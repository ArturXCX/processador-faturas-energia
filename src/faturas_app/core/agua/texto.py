"""Texto EM LAYOUT DE COLUNAS a partir do PDF (PyMuPDF) ou do OCR posicional.

Os extratores de água trabalham sobre texto "em layout", como o `pdftotext -layout` que o projeto original usava: cada
linha impressa vira uma linha de texto e a posição horizontal de cada palavra vira uma coluna de caractere. A diferença é
que aqui o texto sai do próprio PDF (sem arquivo .txt intermediário) e, quando a página é imagem, das palavras do OCR
posicional — o mesmo motor dos borderôs de energia (`borderos._ocr_palavras`). Assim os mesmos regexes servem para PDF de
texto e para PDF digitalizado.

Uso:
    doc = Documento(caminho)          # abre, decide página a página se precisa de OCR
    doc.texto                         # todas as páginas em layout, separadas por "\\f"
    doc.paginas                       # lista de páginas (texto em layout)
    doc.simples                       # texto corrido (get_text) para detecção de palavras-chave
    doc.usou_ocr                      # alguma página veio do OCR
"""
from __future__ import annotations

import os
import re
import statistics
import unicodedata

MIN_TEXTO_PAGINA = 80       # abaixo disso a página é tratada como imagem
COLUNAS_MAX = 260           # largura máxima da linha em caracteres
Y_TOL = 3.0                 # pontos: palavras com y0 até isso de diferença ficam na mesma linha


def sem_acento(s) -> str:
    s = unicodedata.normalize("NFKD", str(s or ""))
    return "".join(c for c in s if not unicodedata.combining(c))


def _linhas(palavras, ytol=Y_TOL):
    """Agrupa palavras (x0, y0, x1, y1, texto, …) em linhas por proximidade vertical (mesma regra dos borderôs)."""
    ws = sorted(palavras, key=lambda t: (t[1], t[0]))
    linhas, atual, cy = [], [], None
    for t in ws:
        if cy is None or abs(t[1] - cy) <= ytol:
            atual.append(t)
            cy = t[1] if cy is None else cy
        else:
            linhas.append(atual)
            atual, cy = [t], t[1]
    if atual:
        linhas.append(atual)
    return linhas


def _largura_char(palavras) -> float:
    """Largura média de um caractere na página (mediana das palavras com 3+ letras), em pontos."""
    ls = [(t[2] - t[0]) / len(t[4]) for t in palavras if len(t[4]) >= 3 and t[2] > t[0]]
    if not ls:
        return 5.0
    return min(7.0, max(3.2, statistics.median(ls)))


def _desrotacionar(palavras):
    """Página com texto em pé (rotacionada 90°): a maioria das palavras é mais alta do que larga. Gira as coordenadas
    para que as linhas voltem a ser horizontais (x ← y, y ← −x)."""
    if not palavras:
        return palavras
    verticais = sum(1 for t in palavras if len(t[4]) >= 3 and (t[3] - t[1]) > 1.5 * (t[2] - t[0]))
    longas = sum(1 for t in palavras if len(t[4]) >= 3)
    if not longas or verticais < 0.6 * longas:
        return palavras
    saida = []
    for t in palavras:
        x0, y0, x1, y1 = t[0], t[1], t[2], t[3]
        saida.append((y0, -x1, y1, -x0) + tuple(t[4:]))
    return saida


def layout(palavras, ytol=Y_TOL) -> str:
    """Texto em layout de colunas a partir das palavras posicionais de UMA página."""
    if not palavras:
        return ""
    palavras = _desrotacionar(palavras)
    cw = _largura_char(palavras)
    saida = []
    x_min = min(t[0] for t in palavras)
    desloc = -x_min if x_min < 0 else 0.0
    for linha in _linhas(palavras, ytol):
        buf = ""
        for t in sorted(linha, key=lambda w: w[0]):
            col = int(round((t[0] + desloc) / cw))
            col = min(col, COLUNAS_MAX)
            if col <= len(buf):
                col = len(buf) + (1 if buf else 0)
            buf = buf.ljust(col) + str(t[4])
        saida.append(buf.rstrip())
    return "\n".join(saida) + "\n"


_VOCABULARIO = ("AGUA", "ESGOTO", "FATURA", "CONSUMO", "VALOR", "VENCIMENTO", "LEITURA", "CONTA", "TOTAL", "CNPJ",
                "REFER", "SANEAMENTO", "HIDR", "MATRICULA", "TARIFA", "DUAM", "SAAE")


def texto_ilegivel(texto: str) -> bool:
    """Página cujo texto embutido não serve: quase nada de letras/dígitos (só espaços ou glifos invisíveis), fonte
    simbólica (maioria de símbolos), nenhuma palavra do vocabulário de faturas, ou camada de texto de scanner ruim
    (tabela de valores em que quase nenhum número tem vírgula: "14477239" no lugar de "144.772,39"). Nesses casos vale o OCR."""
    alnum = sum(1 for c in texto if c.isalnum())
    if alnum < MIN_TEXTO_PAGINA:
        return True
    visiveis = sum(1 for c in texto if not c.isspace())
    if visiveis and alnum / visiveis < 0.6:
        return True
    up = sem_acento(texto).upper()
    if not any(k in up for k in _VOCABULARIO):
        return True
    longos = len(re.findall(r"(?<![\d,.])\d{5,}(?![\d,.])", texto))
    moedas = len(re.findall(r"\d+,\d{2}\b", texto))
    return longos >= 20 and moedas < 0.2 * longos


def _matriz_orientacao(page):
    """Matriz que leva as palavras ao espaço exibido: rotação da página (/Rotate) e, quando o texto foi desenhado de
    cabeça para baixo ou em pé sem /Rotate (direção das linhas no dicionário do PyMuPDF), a rotação equivalente."""
    import fitz
    m = page.rotation_matrix if page.rotation else fitz.Matrix(1, 0, 0, 1, 0, 0)
    try:
        dirs = [tuple(l.get("dir", (1, 0))) for b in page.get_text("dict").get("blocks", []) if b.get("type") == 0 for l in b.get("lines", [])]
    except Exception:  # noqa: BLE001
        return m
    if len(dirs) < 5:
        return m
    dx = sum(d[0] for d in dirs) / len(dirs)
    dy = sum(d[1] for d in dirs) / len(dirs)
    r = page.rect
    if dx < -0.5:                       # texto de cabeça para baixo: gira 180°
        m = m * fitz.Matrix(-1, 0, 0, -1, r.width, r.height) if not page.rotation else fitz.Matrix(-1, 0, 0, -1, r.width, r.height) * m
    elif abs(dy) > 0.5 and not page.rotation:   # texto em pé: gira 90° (lê de baixo para cima → dy < 0)
        m = fitz.Matrix(0, 1, -1, 0, r.height, 0) if dy < 0 else fitz.Matrix(0, -1, 1, 0, 0, r.width)
    return m


class Documento:
    """PDF aberto com texto em layout por página; OCR automático nas páginas-imagem."""

    def __init__(self, caminho: str, ocr: bool = True, dpi: int = 300):
        import fitz
        self.caminho = caminho
        self.nome = os.path.basename(caminho)
        self.paginas: list[str] = []
        self.paginas_ocr: list[bool] = []
        self._simples: list[str] = []
        with fitz.open(caminho) as doc:
            self.n_paginas = doc.page_count
            for i in range(doc.page_count):
                page = doc[i]
                texto = page.get_text() or ""
                usa_ocr = texto_ilegivel(texto)
                if usa_ocr and ocr and _ocr_disponivel():
                    from ..borderos import _ocr_palavras
                    palavras = _ocr_palavras(page, dpi=dpi)
                    self.paginas_ocr.append(True)
                    self.paginas.append(layout(palavras))
                    self._simples.append("\n".join(" ".join(w[4] for w in sorted(l, key=lambda t: t[0]))
                                                   for l in _linhas(palavras)))
                else:
                    palavras = page.get_text("words")
                    m = _matriz_orientacao(page)
                    if not m.is_rectilinear or m != fitz.Matrix(1, 0, 0, 1, 0, 0):
                        # coordenadas das palavras vêm no espaço sem rotação; leva para o espaço exibido
                        palavras = [tuple(fitz.Rect(w[:4]) * m) + tuple(w[4:]) for w in palavras]
                    self.paginas_ocr.append(False)
                    self.paginas.append(layout(palavras))
                    self._simples.append(texto)

    @property
    def usou_ocr(self) -> bool:
        return any(self.paginas_ocr)

    @property
    def texto(self) -> str:
        return "\f".join(self.paginas)

    @property
    def simples(self) -> str:
        return "\n".join(self._simples)

    @property
    def vazio(self) -> bool:
        return len(self.texto.strip()) < MIN_TEXTO_PAGINA


def _ocr_disponivel() -> bool:
    try:
        from .. import ocr
        return ocr.configurar_ocr()
    except Exception:
        return False


# ── utilidades numéricas/datas compartilhadas pelos extratores ─────────────────
_RE_MOEDA = re.compile(r"-?\d{1,3}(?:\.\d{3})*,\d{2}|-?\d+,\d{2}")


def moeda(v) -> float | None:
    """'1.234,56' → 1234.56; None se vazio/inválido. Aceita 'R$ 12,3' (uma casa) e ',50'."""
    if v is None:
        return None
    s = str(v).strip().replace("R$", "").replace(" ", "")
    if not s:
        return None
    if s.startswith(","):
        s = "0" + s
    neg = s.startswith("-") or s.endswith("-")
    s = s.strip("-")
    try:
        if "," in s:
            val = float(s.replace(".", "").replace(",", "."))
        else:
            val = float(s.replace(".", "")) if s.count(".") > 1 or (s.count(".") == 1 and len(s.split(".")[1]) == 3) else float(s)
    except ValueError:
        return None
    return -val if neg else val


def inteiro(v) -> int | None:
    if v is None:
        return None
    s = re.sub(r"\D", "", str(v))
    return int(s) if s else None


def data_iso(v) -> str | None:
    """'30/05/2024' ou '30.05.2024' ou '30-05-24' → '2024-05-30'."""
    if not v:
        return None
    s = str(v).strip()
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return s
    m = re.search(r"(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{2,4})", s)
    if not m:
        return None
    d, mo, a = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if a < 100:
        a += 2000
    if not (1 <= mo <= 12 and 1 <= d <= 31):
        return None
    return f"{a:04d}-{mo:02d}-{d:02d}"


MESES = {"JAN": 1, "FEV": 2, "MAR": 3, "ABR": 4, "MAI": 5, "JUN": 6, "JUL": 7, "AGO": 8, "SET": 9, "OUT": 10, "NOV": 11, "DEZ": 12,
         "JANEIRO": 1, "FEVEREIRO": 2, "MARCO": 3, "ABRIL": 4, "MAIO": 5, "JUNHO": 6, "JULHO": 7, "AGOSTO": 8,
         "SETEMBRO": 9, "OUTUBRO": 10, "NOVEMBRO": 11, "DEZEMBRO": 12}


def competencia(v) -> str | None:
    """'04/2024', '4/2024', 'MAR/2021', 'Marco/2024', '2024-04', '04.2024' → 'AAAA-MM'."""
    if not v:
        return None
    s = sem_acento(str(v)).strip().upper()
    m = re.search(r"(\d{4})-(\d{1,2})", s)
    if m:
        return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}"
    m = re.search(r"(\d{1,2})\s*[/.\-]\s*(\d{4})", s)
    if m and 1 <= int(m.group(1)) <= 12:
        return f"{int(m.group(2)):04d}-{int(m.group(1)):02d}"
    m = re.search(r"([A-Z]{3,9})\s*[/.\-]?\s*(\d{2,4})", s)
    if m and m.group(1) in MESES:
        a = int(m.group(2))
        if a < 100:
            a += 2000
        return f"{a:04d}-{MESES[m.group(1)]:02d}"
    return None


def competencia_por_caminho(caminho: str) -> str | None:
    """Competência pelo nome do arquivo e, faltando o ano no nome, pelo ano da pasta ('2021/FATURA - ABADIÂNIA - AGOSTO- Venc. 23.09.pdf')."""
    nome = os.path.basename(caminho)
    c = competencia_do_nome(nome)
    if c:
        return c
    pasta = os.path.dirname(caminho)
    m_ano = re.search(r"(20\d{2})", os.path.basename(pasta) + " " + os.path.basename(os.path.dirname(pasta)))
    base = sem_acento(os.path.splitext(nome)[0]).upper()
    m_mes = re.search(r"\b(JANEIRO|FEVEREIRO|MARCO|ABRIL|MAIO|JUNHO|JULHO|AGOSTO|SETEMBRO|OUTUBRO|NOVEMBRO|DEZEMBRO|JAN|FEV|MAR|ABR|MAI|JUN|JUL|AGO|SET|OUT|NOV|DEZ)\b", base)
    if m_ano and m_mes:
        return competencia(f"{m_mes.group(1)}/{m_ano.group(1)}")
    return None


def competencia_do_nome(nome: str) -> str | None:
    """Competência pelo nome do arquivo do acervo: 'FATURA Nº 123 - X - MAIO.2022 - VENC. 30.06.2022.pdf', '03-2021', '01.2024'."""
    base = sem_acento(os.path.splitext(nome)[0]).upper()
    m = re.search(r"\b(JANEIRO|FEVEREIRO|MARCO|ABRIL|MAIO|JUNHO|JULHO|AGOSTO|SETEMBRO|OUTUBRO|NOVEMBRO|DEZEMBRO|JAN|FEV|MAR|ABR|MAI|JUN|JUL|AGO|SET|OUT|NOV|DEZ)\s*[.\-_ /]\s*(\d{2,4})\b", base)
    if m:
        return competencia(f"{m.group(1)}/{m.group(2)}")
    m = re.search(r"(?<![\d.])(0[1-9]|1[0-2])[._\-/ ](20\d{2})(?!\d)", base)
    if m:
        return f"{m.group(2)}-{m.group(1)}"
    return None


def digitos(v) -> str:
    return re.sub(r"\D", "", str(v or ""))


def normalizar_descricao(s: str) -> str:
    """Descrição de lançamento sem código, acento, espaços duplos e em maiúsculas: '104 - TARIFA AGUA - PUBLICA' → 'TARIFA AGUA - PUBLICA'."""
    t = sem_acento(str(s or "")).upper().strip()
    t = re.sub(r"^\d{2,4}\s*-\s*", "", t)
    t = re.sub(r"\s+", " ", t)
    return t


def categoria_valor(descricao: str) -> str:
    """Classifica um lançamento em agua / esgoto / taxas / multa_juros / credito / outros pela descrição."""
    d = normalizar_descricao(descricao)
    if any(k in d for k in ("CREDITO", "DESCONTO", "ABATIMENTO")):
        return "credito"
    if any(k in d for k in ("MULTA", "JUROS", "ATUALIZ", "MORA")):
        return "multa_juros"
    if "ESGOTO" in d or "ESG" in d.replace(".", " ").split() or "AFASTAMENTO" in d:
        return "esgoto"
    # tarifas fixas/disponibilidade, impostos e serviços avulsos ficam em "taxas" (total − água − esgoto)
    if any(k in d for k in ("RESIDUO", "SMRSU", "LIXO", "TAXA", "BASIC", "OPERACIONAL", "2A VIA", "RAMAL", "PARCELAMENTO",
                            "IRPJ", "PIS", "COFINS", "RELIGA", "CORTE")):
        return "taxas"
    if any(k in d for k in ("AGUA", "CUSTO MINIMO", "TARIFA MINIMA", "CAPTACAO", "CONSUMO")):
        return "agua"
    if any(k in d for k in ("SERVICO", "SERV.", "SERV ")):
        return "taxas"
    return "outros"


def contexto_regex(padrao: str, texto: str, flags=re.IGNORECASE, grupo=1):
    m = re.search(padrao, texto, flags)
    return m.group(grupo).strip() if m else None
