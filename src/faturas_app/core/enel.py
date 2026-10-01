"""
Processador das faturas ANTIGAS da ENEL Distribuição Goiás (ex-CELG D), anteriores
ao DANF3E — layouts de 2018 a início de 2022, quase sempre DIGITALIZADOS:

  GRUPO_A   "FATURA DO SERVIÇO DE FORNECIMENTO DE ENERGIA ELÉTRICA - GRUPO A":
            quadro "LANÇAMENTOS" com DOIS itens por linha (PRODUTO QUANTIDADE
            TARIFA VALOR ×2), tributos embutidos (ICMS/PIS/COFINS) e, numa
            página à parte, a memória de cálculo da medição.
  B_2020    "NOTA FISCAL/FATURA DE ENERGIA ELÉTRICA" de baixa tensão (2020–2022):
            "ITENS QTD VALOR UNIT. VALOR" ×2 por linha e "TOTAL A PAGAR".
  B_2018    "FATURA DO SERVIÇO DE FORNECIMENTO DE ENERGIA ELÉTRICA - GRUPO B"
            (2018–2019): coluna "LANÇAMENTOS" à direita, um item por linha.

O texto embutido desses PDFs (quando existe) é um OCR de scanner muito ruidoso,
então o texto vem SEMPRE de OCR próprio (Tesseract, 300 dpi):

1. A página 1 inteira é lida com as CAIXAS das palavras; pelo cabeçalho do quadro
   de itens ("PRODUTO", "ITENS", "LANÇAMENTOS") recortam-se as COLUNAS de itens,
   que são lidas de novo, sozinhas e ampliadas — bem mais limpas que a página.
2. Cada leitura (página inteira + colunas em escalas diferentes) gera itens com
   posição; leituras do mesmo item são juntadas e cada item fica com VÁRIOS
   valores candidatos (o OCR troca asterisco por dígito, perde vírgula etc.) —
   mais o valor calculado quantidade × tarifa (a ENEL trunca os centavos).
3. Escolhe-se, entre os candidatos, a combinação cuja SOMA é exatamente o total
   da fatura (e cuja soma dos itens de fornecimento é a base de cálculo do ICMS,
   quando legível). Se nenhuma fecha, a fatura sai com aviso para conferência.

O DANF3E (2022 em diante, layout da Equatorial) não é tratado aqui: vai para
`equatorial.py`, que também faz OCR quando o texto embutido é lixo.
"""
from __future__ import annotations

import math
import os
import re
import unicodedata
from collections import Counter

FORNECEDOR = "ENEL"
DPI = 300


# ──────────────────────────────────────────────────────────────────────────────
# OCR
# ──────────────────────────────────────────────────────────────────────────────
class _Doc:
    """PDF aberto para OCR: rasteriza cada página (300 dpi) só quando precisa."""

    def __init__(self, pdf_path):
        import fitz
        self.caminho = pdf_path
        self.nome = os.path.basename(pdf_path)
        self._img = {}
        self.rot = {}                    # página → giro aplicado (graus, anti-horário), p/ scans de lado
        m = fitz.Matrix(DPI / 72, DPI / 72)
        with fitz.open(pdf_path) as d:
            self._tam = [((p.rect * m).irect.width, (p.rect * m).irect.height) for p in d]
        self.paginas = len(self._tam)

    def tamanho(self, i):
        w, h = self._tam[i]
        return (h, w) if self.rot.get(i, 0) in (90, 270) else (w, h)

    def girar(self, i, graus):
        self.rot[i] = graus % 360
        self._img.pop(i, None)

    def imagem(self, i):
        if i not in self._img:
            import fitz
            from PIL import Image
            with fitz.open(self.caminho) as d:
                pix = d[i].get_pixmap(dpi=DPI)
                img = Image.frombytes('RGB', [pix.width, pix.height], pix.samples)
            if self.rot.get(i):
                img = img.rotate(self.rot[i], expand=True)
            self._img[i] = img
        return self._img[i]


def _giro_osd(doc, pagina):
    """Quanto girar a página para ficar de pé, pela detecção de orientação do Tesseract (0 se falhar)."""
    import pytesseract
    try:
        osd = pytesseract.image_to_osd(doc.imagem(pagina), config='--psm 0')
        return int(re.search(r'Rotate:\s*(\d+)', osd).group(1))
    except Exception:  # noqa: BLE001 — página sem texto suficiente
        return 0


def _tesseract(doc, pagina, caixa=None, esc=1.0, psm='6', variante='rgb', dados=False):
    """OCR de uma página (ou de um recorte dela). Com `dados`, devolve as palavras com
    a caixa em coordenadas da PÁGINA: [(texto, x, y, larg, alt, chave_da_linha)]."""
    import pytesseract
    from PIL import Image, ImageOps
    im = doc.imagem(pagina)
    if caixa:
        im = im.crop(tuple(int(v) for v in caixa))
    if esc != 1.0:
        im = im.resize((round(im.width * esc), round(im.height * esc)), Image.LANCZOS)
    if variante == 'cinza':
        im = ImageOps.grayscale(im)
    elif variante == 'bin':
        im = ImageOps.grayscale(im).point(lambda v: 255 if v > 150 else 0, mode='1').convert('L')
    cfg = f'--psm {psm}'
    if not dados:
        return unicodedata.normalize('NFC', pytesseract.image_to_string(im, lang='por', config=cfg))
    d = pytesseract.image_to_data(im, lang='por', config=cfg, output_type=pytesseract.Output.DICT)
    x0, y0 = (int(caixa[0]), int(caixa[1])) if caixa else (0, 0)
    out = []
    for i, t in enumerate(d['text']):
        t = unicodedata.normalize('NFC', t or '').strip()
        if t:
            out.append((t, x0 + d['left'][i] / esc, y0 + d['top'][i] / esc, d['width'][i] / esc,
                        d['height'][i] / esc, (d['block_num'][i], d['par_num'][i], d['line_num'][i])))
    return out


def _linhas(palavras):
    """Agrupa as palavras do Tesseract em linhas: [(texto, [palavras])], na ordem de leitura."""
    grupos, ordem = {}, []
    for p in palavras:
        k = tuple(p[5])
        if k not in grupos:
            grupos[k] = []
            ordem.append(k)
        grupos[k].append(p)
    return [(' '.join(w[0] for w in grupos[k]), grupos[k]) for k in ordem]


def _texto(palavras):
    return '\n'.join(t for t, _ in _linhas(palavras))


# ──────────────────────────────────────────────────────────────────────────────
# Números do OCR
# ──────────────────────────────────────────────────────────────────────────────
def numero(tok):
    """Quantidade/tarifa/alíquota: '5893,75' → 5893.75 · '0,126870' → 0.12687 · '1.000' → 1000."""
    if tok is None:
        return None
    s = re.sub(r'[^\d,.\-]', '', str(tok))
    if not re.search(r'\d', s):
        return None
    if ',' in s:
        s = s.replace('.', '').replace(',', '.')
    elif s.count('.') == 1 and len(s.split('.')[1]) == 3:
        s = s.replace('.', '')
    try:
        return float(s)
    except ValueError:
        return None


def candidatos_valor(seg):
    """Leituras plausíveis de um valor em R$ escrito pelo OCR, da mais para a menos provável.
    '****2.040,88' → [2040.88, …] · 't1224' → [12.24, 2.24] · '1.861,788' → [1861.78, 18617.88, …]
    · 'rer11126,28' → [11126.28, 1126.28, 126.28] · '607 09' → [607.09, …]. Sinal: '-' colado."""
    s = (seg or '').strip().rstrip('.;:|,').strip()
    m = re.search(r'(-?)\s?(\d[\d.,\s]*\d|\d)$', s)
    if not m:
        return []
    neg = m.group(1) == '-'
    cauda = m.group(2)
    grupos = re.split(r'\s+', cauda)
    leituras = []

    def ler(t):
        t = t.strip()
        mm = re.fullmatch(r'([\d.,]*?)[.,](\d{2})(\d?)', t)
        if mm:
            inteiro = re.sub(r'\D', '', mm.group(1))
            out = [float(f"{inteiro or 0}.{mm.group(2)}")]
            if mm.group(3):                       # dígito a mais depois dos centavos
                out.append(float(re.sub(r'\D', '', t)) / 100)
            return out
        dig = re.sub(r'\D', '', t)
        return [int(dig) / 100] if len(dig) >= 3 else []

    if len(grupos) > 1:
        leituras += ler(''.join(grupos))          # '2 315,92' / '607 09'
        leituras += ler(grupos[-1])
    else:
        leituras += ler(cauda)
    # dígitos espúrios à esquerda (asteriscos lidos como '1', 't'…)
    for v in list(leituras):
        txt = f"{v:.2f}"
        for k in (1, 2):
            if len(txt) - 3 - k >= 1:
                leituras.append(float(txt[k:]))
    vistos, out = set(), []
    for v in leituras:
        v = round(-v if neg else v, 2)
        if v not in vistos:
            vistos.add(v)
            out.append(v)
    return out


def _trunc(x):
    return math.floor(x * 100 + 1e-6) / 100 if x >= 0 else -math.floor(-x * 100 + 1e-6) / 100


def _data(s):
    m = re.search(r'(\d{2})\s?/\s?(\d{2})\s?/\s?(\d{4})', s or '')
    if not m or not (1 <= int(m.group(2)) <= 12 and 1 <= int(m.group(1)) <= 31):
        return None
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"


def _get(pat, txt, g=1, flags=re.I):
    m = re.search(pat, txt or '', flags)
    return m.group(g if m and m.re.groups >= g else 0).strip() if m else None


# ──────────────────────────────────────────────────────────────────────────────
# Itens
# ──────────────────────────────────────────────────────────────────────────────
# tarifa: sempre 6 casas ('0,000000', '27,211840'); o OCR às vezes perde a vírgula
# ('0553150'), põe um dígito a mais ('0,3368760') ou troca um '1' por '/'.
_RE_TARIFA = re.compile(r'(?<![\d.,/])(\d{1,2}[,.]\d{6,7}|\d{7,8}|\d,[\d/]{6})(?![\d,/])')
_RE_MAIUSC = re.compile(r'[A-ZÀ-Ú]{2,}')
_RE_VALOR_TOK = re.compile(r'[*—–-]*-?[\d.]*\d,\d{2}|.*\*{2,}.*')


def _tarifa(tok):
    s = (tok or '').replace('/', '1').replace('.', ',')
    if re.fullmatch(r'\d{1,2},\d{6,7}', s):
        a, b = s.split(',')
        return float(f"{a}.{b[:6]}")
    if re.fullmatch(r'\d{7,8}', s):                  # vírgula perdida: '2437360' = 2,437360
        return float(s[:-6] + '.' + s[-6:])
    return None


def _itens_da_linha(texto, palavras=None):
    """Itens de uma linha do quadro (1 ou 2 por linha), ancorados na coluna da tarifa:
    [{nome, qtd, tarifa, cands, x}] — `x` é a posição (px da página) da tarifa."""
    tars = list(_RE_TARIFA.finditer(texto))
    if not tars:
        return []
    offs, pos = [], 0
    for w in palavras or []:
        offs.append(pos)
        pos += len(w[0]) + 1

    def x_em(ci):
        if not palavras:
            return None
        k = 0
        for i, o in enumerate(offs):
            if o <= ci:
                k = i
        return palavras[k][1]

    itens = []
    ini_nome = 0
    for k, m in enumerate(tars):
        seg_nome = texto[ini_nome:m.start()]
        # se o segmento ainda carrega o fim do item anterior (tarifa ilegível), corta no último nome
        toks = list(re.finditer(r'\S+', seg_nome))
        corte = 0
        for i in range(1, len(toks)):
            if _RE_VALOR_TOK.fullmatch(toks[i - 1].group()) and _RE_MAIUSC.search(toks[i].group()):
                corte = toks[i].start()
        seg_nome = seg_nome[corte:]
        inicio = ini_nome + corte
        mq = re.search(r'(?:^|\s)(\d[\d.]*(?:,\d+)?)[\s\x27\x22`´º°.]*[—–-]*\s*$', seg_nome)
        qtd_txt = mq.group(1) if mq else None
        nome = seg_nome[:mq.start()] if mq else seg_nome
        fim = tars[k + 1].start() if k + 1 < len(tars) else len(texto)
        resto = texto[m.end():fim]
        seg_val, prox = resto, None
        for t in re.finditer(r'\S+', resto):
            if _RE_MAIUSC.search(t.group()) and re.search(r'\d', resto[:t.start()]):
                seg_val, prox = resto[:t.start()], m.end() + t.start()
                break
        nome_l = re.sub(r'^[\W\d_]+', '', nome).strip(' —–-|')
        if len(re.sub(r'[^A-Za-zÀ-ú]', '', nome_l)) >= 2:
            itens.append({'nome': nome_l, 'qtd': numero(qtd_txt) if qtd_txt else None,
                          'tarifa': _tarifa(m.group(1)), 'cands': candidatos_valor(seg_val),
                          'x': x_em(m.start())})
        ini_nome = prox if prox is not None else fim
    return itens


def _posto(n):
    n = (n or '').replace('FORA PONTA', 'FP').replace('PONTA', 'P')
    m = re.search(r'(?:TE|CONSUMO|UFER|DMCR|DEMANDA|AMARELA|VERMELHA|HÍDRICA|HIDRICA|[12])\s*-?\s*(FP|HR|P)(?![A-Z])', n)
    return m.group(1) if m else None


def canonico(nome):
    """Nome do item sem o ruído do OCR, padronizado (para juntar leituras e para o banco).
    Devolve (nome, tipo, unidade)."""
    n = unicodedata.normalize('NFC', nome).upper()
    n = re.sub(r'[“”"\'`´|!]', '', n)
    n = re.sub(r'\s+', ' ', n).strip(' .-—–:;')
    sem = re.sub(r'[^A-Z0-9À-Ú/ ]', ' ', n)
    sem = re.sub(r'\s+', ' ', sem).strip()
    lei = bool(re.search(r'9430|\bLE[I1L]?\b', n))
    forn, fin = 'FORNECIMENTO', 'ITENS FINANCEIROS'
    if re.search(r'CONSUMO\s*K\s*W\s*H?\s*\+|ICMS\s*/?\s*PIS', n):
        return 'CONSUMO', forn, 'kWh'          # 'CONSUMO KWH + ICMS/PIS/COFINS' (grupo B)
    if 'BAND' in sem:
        cor = ('VERMELHA' if 'VERM' in sem else 'AMARELA' if 'AMAR' in sem else
               'ESCASSEZ HÍDRICA' if 'ESCASS' in sem or 'HIDR' in sem else 'VERDE' if 'VERDE' in sem else '')
        pat = _get(r'PAT\w*\s*(\d)', sem)
        if pat and cor == 'VERMELHA':
            cor = f"VERMELHA PATAMAR {pat}"
        compacto = sem.replace(' ', '')
        if 'PARCELA' in sem or 'PARCELATE' in compacto or ' TE ' in f' {sem} ':
            p = _posto(re.sub(r'PARCELA\s*TE', 'PARCELA TE ', sem))
            return re.sub(r'\s+', ' ', f"ADC BAND. {cor} TE {p or ''}").strip(), forn, 'kWh'
        p = _posto(sem)
        return (re.sub(r'\s+', ' ', f"ADC BAND. {cor} {p}") if p else f"ADC BANDEIRA {cor}".strip()), forn, 'kWh'
    if re.search(r'P[I1L]S\b|PASEP', sem) and (lei or 'PASEP' in sem):
        return 'PIS/PASEP LEI 9430(-)', fin, None
    if re.search(r'CO\w?F\w*NS|COFIN', sem) and lei:
        return 'COFINS LEI 9430(-)', fin, None
    if re.search(r'RENDA|IMP\s*DE\b|IRRF|^IR\s*LE', sem):
        return 'IR LEI 9430(-)', fin, None
    if re.search(r'CONTR\w*\s*SOC|LUCRO|CSLL', sem):
        return 'CSLL LEI 9430(-)', fin, None
    if re.search(r'ILUM|CONTRIB', sem):
        return 'CONTRIB. ILUM. PÚBLICA - MUNICIPAL', fin, None
    if 'JUROS' in sem:
        return 'JUROS MORATÓRIA', fin, None
    if 'MULTA' in sem:
        ref = _get(r'(\d{2}/\d{4})', n)
        return (f"MULTA - {ref}" if ref else 'MULTA'), fin, None
    if 'ATUALIZ' in sem:
        if re.search(r'\bD[I1]C\b|\bFIC\b|DMIC', sem):      # correção da compensação de DIC/FIC (crédito)
            return re.sub(r'^[^A-ZÀ-Ú]+', '', n).strip(), fin, None
        return 'ATUALIZAÇÃO MONETÁRIA', fin, None
    sem2 = re.sub(r'\bPARCELA\s*TE', 'PARCELA TE ', sem)
    sem2 = re.sub(r'\b(CONSUMO|UFER|DMCR)(FP|HR|P)\b', r'\1 \2', sem2)
    if 'PARCELA TE' in sem2:
        p = _posto(sem2)
        return f"PARCELA TE {p or ''}".strip(), forn, 'kWh'
    if re.search(r'\bCONSUMO\b', sem2):
        p = _posto(sem2)
        return (f"CONSUMO {p}" if p else 'CONSUMO'), forn, 'kWh'
    if 'DEMANDA' in sem2:
        if 'ULTRA' in sem2:
            return 'DEMANDA ULTRAPASSAGEM', forn, 'kW'
        if 'ISENT' in sem2 or 'ICMS' in sem2:
            return 'DEMANDA ISENTO DE ICMS', forn, 'kW'
        return 'DEMANDA', forn, 'kW'
    if 'UFER' in sem2 or 'YFER' in sem2:
        p = _posto(sem2.replace('YFER', 'UFER'))
        return (f"UFER {p}" if p else 'UFER'), forn, 'kVArh'
    if 'DMCR' in sem2:
        p = _posto(sem2)
        return (f"DMCR {p}" if p else 'DMCR'), forn, 'kVAr'
    limpo = re.sub(r'^[^A-ZÀ-Ú]+', '', n).strip()
    return limpo, fin, None


def _sinal(nome_c, tipo, v, tarifa):
    """A ENEL imprime as retenções da Lei 9.430 com '-' (o OCR às vezes o perde)."""
    if 'LEI 9430' in nome_c or re.search(r'COMPENS|DEVOL|CR[ÉE]DITO|DESCONTO|ESTORNO|\bDIC\b|\bFIC\b|DMIC', nome_c):
        return -abs(v)
    if tipo == 'FORNECIMENTO' and tarifa and tarifa > 0:
        return abs(v)
    if re.search(r'ILUM|JUROS|MULTA|ATUALIZAÇÃO MONETÁRIA', nome_c):
        return abs(v)
    return v


# nomes como os do leitor da Equatorial (correcoes.py), para a série 2018→2026 ficar contínua no Power BI
_RETENCOES = ('PIS/PASEP LEI 9430(-)', 'COFINS LEI 9430(-)', 'IR LEI 9430(-)', 'CSLL LEI 9430(-)')


# ──────────────────────────────────────────────────────────────────────────────
# Leituras do quadro de itens
# ──────────────────────────────────────────────────────────────────────────────
def _acha(palavras, pat):
    return [p for p in palavras if re.fullmatch(pat, p[0], re.I)]


def _recortes(palavras, W, H, lay):
    """Caixas das colunas de itens (px da página) e o y onde termina o quadro."""
    if lay == 'B_2018':
        lan = _acha(palavras, r'LAN\S{2,4}MENTOS')
        if not lan:
            return [], None
        q = [p for p in _acha(palavras, r'.UANTIDADE|TARIFA') if lan[0][2] < p[2] < lan[0][2] + 100]
        topo = q[0] if q else lan[0]
        y0 = topo[2] + topo[4] + 1
        fim = [p for p in _acha(palavras, r'HIST\S+RICO|GR\S?FICO|RESERVADO|TRIBUTO') if p[2] > y0 + 60]
        y1 = min([p[2] - 4 for p in fim] + [y0 + int(0.16 * H)])
        return [(max(lan[0][1] - 30, 0), y0, W, y1)], y1
    if lay == 'GRUPO_A':
        cab = sorted(_acha(palavras, r'PRODUTO'), key=lambda p: (p[2], p[1]))
        fim_pat = r'COMPOSI\S*'
    else:
        cab = sorted(_acha(palavras, r'ITENS'), key=lambda p: (p[2], p[1]))
        fim_pat = r'TOTAL\S*'
    cab = [p for p in cab if abs(p[2] - cab[0][2]) < 40] if cab else []
    if not cab:
        lan = _acha(palavras, r'LAN\S{2,4}MENTOS')
        if lay != 'GRUPO_A' or not lan:
            return [], None
        # cabeçalho 'PRODUTO QUANTIDADE TARIFA VALOR' ilegível: as colunas dividem a página ao meio
        y0 = lan[0][2] + lan[0][4] + 55
        fim = [p for p in _acha(palavras, r'COMPOSI\S*') if p[2] > y0]
        y1 = min([p[2] - 4 for p in fim] + [y0 + int(0.22 * H)])
        meio = int(W * 0.497)
        return [(max(lan[0][1] - 30, 0), y0, meio, y1), (meio, y0, W, y1)], y1
    fim = [p for p in _acha(palavras, fim_pat) if p[2] > cab[0][2] + 30]
    xs = sorted(p[1] for p in cab)
    y0 = min(p[2] + min(p[4], 30) for p in cab) + 1
    y1 = min([p[2] - 4 for p in fim] + [y0 + int(0.22 * H)])
    if len(xs) >= 2 and xs[1] - xs[0] > W * 0.3:
        meio = xs[1] - 15
        return [(max(xs[0] - 30, 0), y0, meio, y1), (meio, y0, W, y1)], y1
    return [(max(xs[0] - 30, 0), y0, W, y1)], y1


def _leitura(palavras, y0=None, y1=None, x0=None):
    """Itens de uma leitura (lista de palavras) entre y0 e y1 (e à direita de x0): [{…, x, y}]."""
    out = []
    for _, ws in _linhas(palavras):
        if x0 is not None:
            ws = [w for w in ws if w[1] >= x0 - 10]
        if not ws:
            continue
        texto = ' '.join(w[0] for w in ws)
        y = min(w[2] for w in ws)
        if (y0 is not None and y < y0 - 25) or (y1 is not None and y > y1):
            continue
        for it in _itens_da_linha(texto, ws):
            it['y'] = y
            out.append(it)
    return out


def _coluna(x, cols):
    if x is None or not cols:
        return 0
    for i, c in enumerate(cols):
        if c[0] - 10 <= x < c[2]:
            return i
    return min(range(len(cols)), key=lambda i: abs(x - (cols[i][0] + cols[i][2]) / 2))


def _juntar(leituras, cols):
    """Junta as leituras do mesmo item (mesmo nome canônico, mesma linha e coluna)."""
    grupos = []
    for n_leit, itens in enumerate(leituras):
        for it in itens:
            nome, tipo, unid = canonico(it['nome'])
            if not nome:
                continue
            col = _coluna(it['x'], cols)
            alvo = None
            for g in grupos:
                if g['nome'] == nome and g['col'] == col and abs(g['y'] - it['y']) < 28 and n_leit not in g['leituras']:
                    alvo = g
                    break
            if alvo is None:
                alvo = {'nome': nome, 'tipo': tipo, 'unidade': unid, 'col': col, 'y': it['y'], 'leituras': {},
                        'qtds': [], 'tarifas': []}
                grupos.append(alvo)
            alvo['leituras'][n_leit] = it['cands']
            if it['qtd'] is not None:
                alvo['qtds'].append(it['qtd'])
            if it['tarifa'] is not None:
                alvo['tarifas'].append(it['tarifa'])
    grupos.sort(key=lambda g: (round(g['y'] / 30), g['col']))
    return grupos


def _mais_comum(vals):
    vals = [v for v in vals if v is not None]
    return Counter(vals).most_common(1)[0][0] if vals else None


def _candidatos_grupo(g, n_leituras, qtd_posto):
    """{centavos: pontos} de um item. Leituras que concordam pontuam mais; o valor
    calculado (quantidade × tarifa, truncado) pontua quando bate com alguma leitura."""
    pontos = Counter()
    tarifa = _mais_comum(g['tarifas'])
    qtd = _mais_comum(g['qtds'])
    if g['tipo'] == 'FORNECIMENTO' and qtd_posto and (qtd is None or g['qtds'].count(qtd) < 2):
        qtd = qtd_posto
    for cands in g['leituras'].values():
        for i, v in enumerate(cands):
            v = _sinal(g['nome'], g['tipo'], v, tarifa)
            pontos[round(v * 100)] += 3 if i == 0 else 1
    if tarifa and tarifa > 0 and qtd:
        calc = []
        for q in (qtd, qtd / 10, qtd / 100, qtd / 1000):
            calc += [_trunc(q * tarifa), round(q * tarifa, 2)]
        lidos = set(pontos)
        bateu = False
        for c in calc[:2]:
            tol = round(2 + abs(c) * 0.005)
            for v in lidos:
                if abs(v - round(c * 100)) <= tol:
                    pontos[v] += 4
                    bateu = True
        if not bateu:
            for c in calc[:2]:
                pontos[round(c * 100)] += 2
        for c in calc[2:]:
            if round(c * 100) in lidos:
                pontos[round(c * 100)] += 2
    g['tarifa'] = tarifa
    g['qtd'] = qtd
    if len(g['leituras']) < max(2, n_leituras // 2):
        pontos[None] = 0                          # visto só numa leitura: pode ser lixo
    return pontos


def _escolher(grupos, alvo_cent, limite=20000):
    """Programação dinâmica: um candidato por item cuja soma dá `alvo_cent`, com o máximo
    de pontos. Sem solução exata, aceita a mais próxima (até 2 centavos).
    Devolve (valores escolhidos, desvio em centavos, pontos) ou (None, None, None)."""
    if not grupos:
        return ([], 0, 0) if alvo_cent == 0 else (None, None, None)
    estados = {0: (0, None)}
    hist = []
    for g in grupos:
        novos = {}
        for s, (p, _) in estados.items():
            for v, pv in g['_pontos'].items():
                s2 = s + (v or 0)
                p2 = p + pv
                if s2 not in novos or novos[s2][0] < p2:
                    novos[s2] = (p2, (s, v))
        if len(novos) > limite:
            novos = dict(sorted(novos.items(), key=lambda kv: -kv[1][0])[:limite])
        hist.append(novos)
        estados = novos
    melhor = next((alvo_cent + d for d in (0, 1, -1, 2, -2) if alvo_cent + d in estados), None)
    if melhor is None:
        return None, None, None
    pontos = estados[melhor][0]
    escolha, s = [], melhor
    for novos in reversed(hist):
        _, (s_ant, v) = novos[s]
        escolha.append(v)
        s = s_ant
    escolha.reverse()
    return escolha, melhor - alvo_cent, pontos


def _melhor_isolado(g):
    p = {v: q for v, q in g['_pontos'].items() if v is not None}
    return max(p.items(), key=lambda kv: kv[1])[0] if p else None


def _reconciliar(grupos, n_leit, totais, bases):
    """Escolhe o valor de cada item: soma = total (e fornecimento = base, quando houver).
    `totais`/`bases`: [(centavos, peso)]. Entre os totais candidatos fica o que fecha com
    mais pontos; um total que só fecha trocando muitos itens por leituras improváveis
    (ex.: um 'total' que é lixo do OCR) é recusado.
    Devolve (total escolhido em centavos, desvio) ou (None, None)."""
    qtd_posto = {}
    for g in grupos:
        if g['tipo'] == 'FORNECIMENTO':
            qtd_posto.setdefault((g['unidade'], _posto(g['nome']) or '-'), []).extend(g['qtds'])
    qtd_posto = {p: _mais_comum(v) for p, v in qtd_posto.items()}
    for g in grupos:
        qp = qtd_posto.get((g['unidade'], _posto(g['nome']) or '-')) if g['tipo'] == 'FORNECIMENTO' else None
        g['_pontos'] = _candidatos_grupo(g, n_leit, qp)
    maximo = sum(max(g['_pontos'].values()) for g in grupos if g['_pontos'])
    forn = [g for g in grupos if g['tipo'] == 'FORNECIMENTO']
    outros = [g for g in grupos if g['tipo'] != 'FORNECIMENTO']
    solucoes = []
    for tot, peso in totais:
        for base, peso_b in bases:
            e1, d1, p1 = _escolher(forn, base)
            if e1 is None:
                continue
            e2, d2, p2 = _escolher(outros, tot - base - d1)
            if e2 is None:
                continue
            solucoes.append((p1 + p2 + 2 * peso + peso_b - 5 * abs(d1 + d2), p1 + p2, tot, d1 + d2, e1 + e2, forn + outros))
        e, d, p = _escolher(grupos, tot)
        if e is not None:
            solucoes.append((p + 2 * peso - 5 * abs(d), p, tot, d, e, grupos))
    solucoes = [s for s in solucoes if s[1] >= 0.75 * maximo]
    if solucoes:
        _, _, tot, d, escolha, ordem = max(solucoes, key=lambda s: s[0])
        for g, v in zip(ordem, escolha):
            g['valor'] = v
        return tot, d
    for g in grupos:
        g['valor'] = _melhor_isolado(g)
    # uma linha de retenção sumiu da leitura: as quatro da Lei 9.430 vêm em conjuntos (uma por base
    # tributada), então a que aparece menos vezes é a que falta — se a diferença for pequena e negativa
    tipos = Counter(g['nome'] for g in grupos if g['nome'] in _RETENCOES)
    if len(tipos) >= 3:
        for tot, peso in totais:
            falta_v = tot - sum(g['valor'] or 0 for g in grupos)
            if peso < 3 or falta_v >= 0 or -falta_v > 0.01 * tot:
                continue
            falta = min(_RETENCOES, key=lambda t: tipos.get(t, 0))
            if tipos.get(falta, 0) < max(tipos.values()):
                grupos.append({'nome': falta, 'tipo': 'ITENS FINANCEIROS', 'unidade': None, 'col': 0,
                               'y': max(g['y'] for g in grupos) + 1, 'leituras': {}, 'qtds': [], 'tarifas': [],
                               '_pontos': Counter(), 'qtd': None, 'tarifa': None, 'valor': falta_v,
                               'pela_diferenca': True})
                return tot, 0
    # um único item ilegível (sem leitura confiável) fecha pela diferença com um total bem lido
    for tot, peso in totais:
        if peso < 3:
            continue
        fracos = sorted((g for g in grupos if max(g['_pontos'].values(), default=0) <= 3),
                        key=lambda g: max(g['_pontos'].values(), default=0))
        for g in fracos:
            resto = sum(h['valor'] or 0 for h in grupos if h is not g)
            v = tot - resto
            if _plausivel(g, v, tot):
                g['valor'] = v
                g['pela_diferenca'] = True
                return tot, 0
    return None, None


def _plausivel(g, v_cent, tot_cent):
    """Um valor deduzido do total cabe neste item? (sinal e ordem de grandeza)"""
    if v_cent == 0:
        return False
    if 'LEI 9430' in g['nome']:
        return v_cent < 0 and -v_cent < 0.1 * tot_cent
    if re.search(r'ILUM|JUROS|MULTA|ATUALIZ', g['nome']):
        return 0 < v_cent < 0.1 * tot_cent
    if g['tipo'] == 'FORNECIMENTO':
        if not (0 < v_cent < tot_cent):
            return False
        if g.get('tarifa') and g.get('qtd'):
            v = v_cent / 100
            return any(abs(g['qtd'] / f * g['tarifa'] - v) <= max(0.05, v * 0.01) for f in (1, 10, 100, 1000))
        return True
    return abs(v_cent) < 0.2 * tot_cent


# ──────────────────────────────────────────────────────────────────────────────
# Layout e cabeçalho
# ──────────────────────────────────────────────────────────────────────────────
def layout(txt):
    up = (txt or '').upper()
    if ('DOCUMENTO AUXILIAR DA NOTA FISCAL' in up or 'CHAVE DE ACESSO' in up or 'DANF3E' in up
            or re.search(r'DOCUMENTO\s+\S+\s+DA\s+NOTA\s+FISCAL|NOTA\s+FISCAL\s+N\S{0,2}\s*\d{6,9}\s*-\s*S[ÉE]RIE'
                         r'|ITENS\s+DE\s+FATURA|EQUATORIAL\s+GOI', up)):
        return 'DANF3E'
    if re.search(r'ITENS\s+QTD', up) or 'DADOS DO CLIENTE/UNIDADE' in up or 'NOTA FISCAL/FATURA DE ENERGIA' in up:
        return 'B_2020'
    if (re.search(r'PRODUTO\s+QUANTIDADE', up) or re.search(r'ENERGIA\s+EL\S+\s*-\s*GRUPO\s*A\b', up)
            or (re.search(r'\bUC\s*:\s*\d{7}', up) and re.search(r'\bTHS\b|DEMANDA', up))):
        return 'GRUPO_A'
    if re.search(r'LAN\S{2,4}MENTOS', up):
        return 'B_2018'
    return None


def _competencia(txt):
    for pat in (r'M[ÊE]S\s+DE\s+REFER\S*\s+(\d{2})\s*/\s*(\d{4})',
                r'M[ÊE]S\s+REFERENTE\s+(\d{2})\s*/\s*(\d{4})',
                r'Conta referente[^\n]*\n[^\n]*?\d{2}/\d{2}/\d{4}\s+(\d{2})\s*/\s*(\d{4})',
                r'(?<!\d)20\d{11}\s+\d{2}/\d{2}/\d{4}\s+(\d{2})\s*/\s*(\d{4})',
                r'M[ÊE]S\s+DE\s+REFER[^\n]*\n[^\n]*?(\d{2})\s*/\s*(\d{4})\s+\d{2}/\d{2}/\d{4}'):
        m = re.search(pat, txt or '', re.I)
        if m and 1 <= int(m.group(1)) <= 12 and 2015 <= int(m.group(2)) <= 2030:
            return f"{m.group(2)}-{m.group(1)}"
    return None


def _cabecalho(lay, p1, resto):
    """Campos da fatura a partir do texto da página 1 (`p1`) e das demais (`resto`)."""
    txt = p1 + '\n' + resto
    f = {}
    f['numero_fatura'] = _get(r'(?<![\d.])(20[12]\d{10})(?![\d.])', p1)
    if lay == 'GRUPO_A':
        m = re.search(r'NOTA\s+FISCAL\s+(\d{5,9})\s+(\d)\s+(\d{2}/\d{2}/\d{4})(?:\s+(A\d\w?))?', p1, re.I)
        if m:
            f['numero_nf'], f['serie_nf'], f['data_emissao'], f['grupo'] = m.group(1), m.group(2), _data(m.group(3)), m.group(4)
        f['id_uc'] = _get(r'\bUC\s*:?\s*(\d{7,10})', p1)
        m = re.search(r'VALOR\s+TOTAL[^\n]*\n(?:[^\n]*\n){0,2}?[^\n]*?(\d{2}\s?/\s?\d{4})\s+(\d{2}/\d{2}/\d{4})\s+R\s?\$\s*([^\n]*)', p1, re.I)
        if m:
            f['data_vencimento'] = _data(m.group(2))
            f['_total'] = candidatos_valor(m.group(3))
        f['demanda_contratada_kw'] = numero(_get(r'\bDEMANDA\s+(\d{2,4}(?:,\d+)?)\s*$', p1, flags=re.I | re.M))
        f['perdas_transformacao_pct'] = numero(_get(r'PERDA\S*\s+(\d+[.,]\d+)\s*%', p1))
        f['estrutura'] = _get(r'\b(THS\s*(?:VERDE|AZUL))', p1)
        f['medidor'] = _get(r'MEDIDOR\s*ELETR\S*\s*\W*\s*(\d{6,10}-\d)', p1) or _get(r'MEDIDOR:\s*(\d{6,10}-\d)', txt)
        f['data_leitura_atual'] = _data(_get(r'LEITURA\s+ATUAL\s+(\d{2}/\d{2}/\d{4})', p1))
        f['data_leitura_anterior'] = _data(_get(r'LEITURA\s+ANTERIOR\s*\W*\s*(\d{2}/\d{2}/\d{4})', p1))
        f['data_proxima_leitura'] = _data(_get(r'PR[ÓO]XIMA\s+LEITURA\s*\W*\s*(\d{2}/\d{2}/\d{4})', p1))
        f['numero_dias_leitura'] = _get(r'N[ÚU]MERO\s+DE\s+DIAS\s+(\d{1,3})\b', p1)
    elif lay == 'B_2020':
        m = re.search(r'(\d{2}/\d{2}/\d{4})\s+(\d{6,9})\s+(\S)\s+([\d.,]+)\s+(\d{1,2})\s*%\s+([\d.,]+)', p1)
        if m:
            f['data_emissao'], f['numero_nf'] = _data(m.group(1)), m.group(2)
            f['serie_nf'] = m.group(3) if m.group(3).isdigit() else None
            f['_icms'] = (m.group(4), m.group(5), m.group(6))
        m = re.search(r'(?<!\d)(20[12]\d{10})\s+(\d{2}/\d{2}/\d{4})\s+(\d{2})\s*/\s*(\d{4})', txt)
        if m:
            f['numero_fatura'] = f.get('numero_fatura') or m.group(1)
            f.setdefault('data_emissao', _data(m.group(2)))
        m = re.search(r'(?<!\d)(\d{8})\s+(\d{2}/\d{2}/20\d{2})\s+R?\$?\s*([\d.,*]+)', txt)
        if m:
            f['id_uc'], f['data_vencimento'] = m.group(1), _data(m.group(2))
            f['_total_canhoto'] = candidatos_valor(m.group(3))
        m = re.search(r'TOTAL\s*A\s*PAGAR\s*(?:\(R\$\))?\s*[^\d\n]{0,8}([\d.,\s*]+)', p1, re.I)
        if m:
            f['_total'] = candidatos_valor(m.group(1))
        f['medidor'] = _get(r'\b(\d{6,9}-\d)\b', txt)
        f['data_leitura_atual'] = _data(_get(r'Leitura\s+atual\s*\W*\s*(\d{2}/\d{2}/\d{4})', txt))
        f['data_leitura_anterior'] = _data(_get(r'Leitura\s+anterior\s*\W*\s*(\d{2}/\d{2}/\d{4})', txt))
        f['data_proxima_leitura'] = _data(_get(r'Pr[óo]xima\s+leitura\s*\W*\s*(\d{2}/\d{2}/\d{4})', txt))
        f['tipo_fornecimento'] = _get(r'(TRIF[ÁA]SICO|MONOF[ÁA]SICO|BIF[ÁA]SICO)', p1)
        f['subgrupo'] = _get(r'Subgrupo\s+(B\d)', p1)
    else:  # B_2018
        m = re.search(r'(?<![\d/])(\d{6,8})\s+(\d)\s+(\d{2}/\d{2}/\d{4})(?:\s+[B8](\d))?', p1)
        if m:
            f['numero_nf'], f['serie_nf'], f['data_emissao'] = m.group(1), m.group(2), _data(m.group(3))
            f['subgrupo'] = f"B{m.group(4)}" if m.group(4) else None
        f['id_uc'] = _get(r'(?<![\dA-Z])[O0]{2}(\d{8})(?!\d)', p1)
        m = re.search(r'VALOR\s+TOTAL[^\n]*\n(?:[^\n]*\n){0,2}?[^\n]*?(\d{2}/?\d{2}/?\d{4})\s*\W*\s*R\s?\$\s*([^\n]*)', p1, re.I)
        if m:
            f['data_vencimento'] = _data(re.sub(r'(\d{2})/?(\d{2})/?(\d{4})', r'\1/\2/\3', m.group(1)))
            f['_total'] = candidatos_valor(m.group(2))
        f['data_leitura_atual'] = _data(_get(r'DATA\s+DA\s+LEITU\S*\s+(?:ATUAL\s+)?(\d{2}/\d{2}/\d{4})', p1))
        f['data_leitura_anterior'] = _data(_get(r'LEITURA\s*\W*\s*\S*ERIOR\s*\W*\s*(\d{2}/\d{2}/\d{4})', p1))
        f['data_proxima_leitura'] = _data(_get(r'PR[ÓO]XIMA\s+LEITURA\s*\W*\s*(\d{2}/\d{2}/\d{4})', p1))
        f['numero_dias_leitura'] = _get(r'DIAS\s+FATURADO\S*\s+(\d{1,3})\b', p1)
        f['medidor'] = _get(r'MEDIDOR[^\n]{0,12}?(\d{6,8}-\d)', p1)
        f['leitura_atual'] = _get(r'LEITURA\s+ATUAL\s+(\d{3,7})\b', p1)
        f['leitura_anterior'] = _get(r'LEITURA\s+ANTERIOR\s+(\d{3,7})\b', p1)
        f['tipo_fornecimento'] = _get(r'(TRIF[ÁA]SICO|MONOF[ÁA]SICO|BIF[ÁA]SICO)', p1)
    f['competencia'] = _competencia(p1) or _competencia(resto)
    if not f.get('competencia') and f.get('data_emissao') and lay != 'GRUPO_A':
        f['competencia'] = f['data_emissao'][:7]          # B: a conta é emitida no próprio mês de referência
    if not f.get('id_uc'):
        deb = _get(r'(?:c[óo]digo|D[ÉE]B\S*\s*AUTO\S*)[^\n\d]{0,30}0*(\d{2,4}\s?\d{3,6})', txt)
        deb = re.sub(r'\s', '', deb or '')
        f['id_uc'] = deb if len(deb) == 8 else None
    return f


def _bases(lay, p1, f):
    """Candidatos à base de cálculo do ICMS (= soma dos itens de fornecimento): {centavos: pontos}.
    Só pontua forte a base cujo imposto (base × alíquota, truncado) também foi lido."""
    c = Counter()
    if lay == 'B_2020' and f.get('_icms'):
        b, a, v = f['_icms']
        for cb in candidatos_valor(b):
            for cv in candidatos_valor(v)[:2]:
                if numero(a) and abs(_trunc(cb * numero(a) / 100) - cv) <= 0.011:
                    c[round(cb * 100)] += 5
    for linha in p1.splitlines():
        m = re.search(r'\b(ICMS|PIS/?PASEP|COFINS)\s+(\d[\d,]*)\s*%\s*(.*)$', linha)
        if not m or 'LEI' in linha.upper():
            continue
        partes = [p for p in re.split(r'R\s?\$', m.group(3)) if re.search(r'\d', p)]
        if len(partes) >= 2:
            aliq = numero(m.group(2))
            for cb in candidatos_valor(partes[0]):
                for cv in candidatos_valor(partes[1])[:3]:
                    if aliq and abs(_trunc(cb * aliq / 100) - cv) <= 0.011:
                        c[round(cb * 100)] += 4
    return c


def _tributos(lay, p1, f, base_cent):
    """ICMS/PIS/COFINS destacados (já embutidos nos itens): valor = base × alíquota, truncado."""
    aliq = {}
    for linha in p1.splitlines():
        if 'LEI' in linha.upper():
            continue
        for nome, pat in (('ICMS', r'\bICMS\s+(\d{1,2})\s*%'), ('PIS/PASEP', r'PIS/?PASEP\s+[^\n%]*?(\d[,.]\d{3,4})\s*%'),
                          ('COFINS', r'COFINS\s+[^\n%]*?(\d[,.]\d{3,4})\s*%')):
            a = numero(_get(pat, linha))
            if a is not None and nome not in aliq:
                aliq[nome] = a
    if lay == 'B_2020' and f.get('_icms'):
        aliq.setdefault('ICMS', numero(f['_icms'][1]))
    if base_cent is None:
        return []
    base = base_cent / 100
    return [{'Tributo': nome, 'Base (R$)': base, 'Aliquota (%)': f"{aliq[nome]}%",
             'Valor (R$)': _trunc(base * aliq[nome] / 100)}
            for nome in ('PIS/PASEP', 'ICMS', 'COFINS') if aliq.get(nome)]


# ──────────────────────────────────────────────────────────────────────────────
# Medição
# ──────────────────────────────────────────────────────────────────────────────
_GRANDEZAS_A = (('CONSUMO', 'ENERGIA ATIVA - KWH'), ('DEMANDA', 'DEMANDA - KW'), ('REATIVO', 'ENERGIA REATIVA - KWH'),
                ('UFER', 'UFER'), ('DMCR', 'DMCR'))
_CONSTANTES = (0.02, 0.08, 2.0, 8.0, 0.2, 0.8, 1.0, 0.4, 4.0, 0.04)


def _medicao_grupo_a(texto, perdas, medidor, consumo_itens):
    """Memória de cálculo: 'CONSUMO LIDO 177644 — 161175 = 16469 X 0,02 = 337,61' — três blocos
    (PONTA, FORA PONTA, RESERVADO). As leituras são conferidas pela própria conta:
    (atual − anterior) × constante × (1 + perdas) = resultado."""
    fator = 1 + (perdas or 0) / 100
    out = []
    vistos = Counter()
    for linha in texto.splitlines():
        u = linha.upper()
        g = next(((k, nome) for k, nome in _GRANDEZAS_A if re.search(rf'{k}\s*LID', u)), None)
        if not g or 'ULTR' in u:
            continue
        bloco = vistos[g[0]]
        vistos[g[0]] += 1
        if bloco > 2:
            continue
        posto = ('PONTA', 'FORA PONTA', 'RESERVADO')[bloco]
        nums = re.findall(r'\d[\d.,]*', re.sub(r'^.*?LID[OA]\S*\s*(?:\(K\w*\))?', '', u))
        ints = [int(n) for n in nums[:3] if re.fullmatch(r'\d+', n)]
        atual = anterior = dif = None
        if len(ints) >= 2:
            atual, anterior = ints[0], ints[1]
            dif = ints[2] if len(ints) >= 3 else None
            if dif is not None and atual - anterior != dif and anterior + dif >= 0:
                atual = anterior + dif               # o OCR perdeu/trocou um dígito da leitura atual
        resultado = numero(nums[-1]) if len(nums) >= 5 else None
        const = None
        if dif is not None and resultado:
            const = next((c for c in _CONSTANTES if abs(dif * c * fator - resultado) <= max(0.02, resultado * 0.002)), None)
        consumo = resultado
        if const is None:                            # a conta não fecha: leituras ilegíveis
            atual = anterior = None
        chave = {'PONTA': 'P', 'FORA PONTA': 'FP', 'RESERVADO': 'HR'}[posto]
        if g[0] == 'CONSUMO' and consumo_itens.get(chave):
            consumo = consumo_itens[chave]
        elif const is None:
            continue
        out.append({'Grandezas': g[1], 'Postos horarios': posto, 'Leitura Anterior': anterior, 'Leitura Atual': atual,
                    'Const Medidor': const, 'Consumo kWh': consumo, 'Medidor': medidor})
    return [r for r in out if r['Leitura Atual'] is not None or r['Consumo kWh']]


# ──────────────────────────────────────────────────────────────────────────────
# Processamento
# ──────────────────────────────────────────────────────────────────────────────
def _pagina_principal(doc):
    """(página, palavras, layout) do corpo da fatura. Há scans com o verso (canhoto/endereço)
    antes da página principal e scans de lado ou de cabeça para baixo."""
    lidas = []
    for i in range(doc.paginas):
        pal = _tesseract(doc, i, dados=True)
        lay = layout(_texto(pal))
        if lay:
            return i, pal, lay
        lidas.append(i)
    for i in lidas:
        giro = _giro_osd(doc, i)
        for g in ([giro] if giro else []) + [180]:
            doc.girar(i, -g)
            pal = _tesseract(doc, i, dados=True)
            lay = layout(_texto(pal))
            if lay:
                return i, pal, lay
            doc.girar(i, 0)
    return 0, _tesseract(doc, 0, dados=True), None


def _ler_itens(doc, pp, palavras, lay, extra=False):
    """Leituras do quadro de itens: a página inteira e as colunas recortadas (1× e 1,5×;
    com `extra`, também binarizada e em tons de cinza 2×)."""
    W, H = doc.tamanho(pp)
    cols, y_fim = _recortes(palavras, W, H, lay)
    if not cols:
        return [_leitura(palavras)], cols
    leituras = [_leitura(palavras, min(c[1] for c in cols), y_fim, cols[0][0] if lay == 'B_2018' else None)]
    modos = [(1.0, 'rgb'), (1.5, 'rgb')] + ([(1.5, 'bin'), (2.0, 'cinza')] if extra else [])
    for esc, var in modos:
        itens = []
        for c in cols:
            itens += _leitura(_tesseract(doc, pp, c, esc=esc, variante=var, dados=True))
        leituras.append(itens)
    return leituras, cols


def _abaixo(doc, pp, palavras, rotulo, faixa=(0.0, 1.0), altura=110, largura=None, esc=2.0, variante='cinza'):
    """Relê, ampliado, a faixa logo abaixo de um rótulo — valores em caixas sombreadas ou em
    fonte de máquina de escrever que o OCR da página inteira perde ('VENCIMENTO' → '30/03/2021')."""
    W, H = doc.tamanho(pp)
    for p in _acha(palavras, rotulo):
        if not faixa[0] * H <= p[2] <= faixa[1] * H:
            continue
        mesma_linha = [q[1] for q in palavras if abs(q[2] - p[2]) < 20 and q[1] <= p[1]]
        x0 = (min(mesma_linha) if largura is None and mesma_linha else p[1]) - 40
        x1 = W if largura is None else min(W, p[1] + largura)
        caixa = (max(0, x0), p[2] + p[4] + 2, x1, min(H, p[2] + p[4] + altura))
        return _tesseract(doc, pp, caixa, esc=esc, variante=variante)
    return ''


def _total_recortado(doc, pp, palavras):
    """O valor total fica num quadro destacado ('VALOR TOTAL' / 'R$*****747,90'): relê só ele, ampliado."""
    W, H = doc.tamanho(pp)
    for p in _acha(palavras, r'TOTAL'):
        if p[2] > H * 0.45:
            continue
        valor = [q for q in _acha(palavras, r'VALOR') if abs(q[2] - p[2]) < 25 and 0 < p[1] - q[1] < 400]
        x0 = (valor[0][1] if valor else p[1] - 150) - 120
        base = p[2] + min(p[4], 32)
        # recorte JUSTO no valor (sem as bordas do quadro, que confundem o Tesseract), em cores
        caixa = (max(x0, 0), base + 3, min(p[1] + p[3] + 180, W), min(base + 58, H))
        larga = (max(x0 - 80, 0), p[2] - 4, W, min(p[2] + p[4] + 130, H))
        cands = []
        for cx, esc, var in ((caixa, 1.0, 'rgb'), (caixa, 2.0, 'rgb'), (larga, 2.0, 'cinza'), (larga, 1.5, 'bin')):
            m = re.search(r'R\s?\$\s*([^\n]*)', _tesseract(doc, pp, cx, esc=esc, variante=var))
            if m:
                cands += [v for v in candidatos_valor(m.group(1)) if v not in cands]
        return cands
    return []


def _extras_b2020(doc, pp, palavras):
    """Canhoto ('N. do Cliente | Data da Emissão | Conta referente à' e 'N. da Instalação |
    VENCIMENTO | TOTAL A PAGAR') e quadro 'Dados da Conta', relidos em recorte."""
    return {'canhoto1': _abaixo(doc, pp, palavras, r'refer\S*', faixa=(0.55, 1.0), altura=95),
            'canhoto2': _abaixo(doc, pp, palavras, r'VENCIMENTO', faixa=(0.55, 1.0), altura=95),
            'conta': _abaixo(doc, pp, palavras, r'VENCIMENTO', faixa=(0.0, 0.25), altura=150, largura=900)}


def _aplicar_extras_b2020(f, ext):
    m = re.search(r'(20[12]\d{10})\D{1,12}(\d{2}/\d{2}/\d{4})\D{1,12}(\d{2})\s*/\s*(\d{4})', ext.get('canhoto1') or '')
    if m:
        f['numero_fatura'] = m.group(1)
        f['data_emissao'] = f.get('data_emissao') or _data(m.group(2))
        if 1 <= int(m.group(3)) <= 12:
            f['competencia'] = f"{m.group(4)}-{m.group(3)}"
    m = re.search(r'(?<!\d)(\d{8})\D{1,12}(\d{2}/\d{2}/\d{4})\D{1,12}([\d.,]+)', ext.get('canhoto2') or '')
    if m:
        f['id_uc'] = f.get('id_uc') or m.group(1)
        f['data_vencimento'] = f.get('data_vencimento') or _data(m.group(2))
        f['_total_canhoto'] = candidatos_valor(m.group(3))
    conta = ext.get('conta') or ''
    m = re.search(r'(\d{2}/\d{2}/\d{4})\s+(?:R\$\s*)?([\d.,]+)', conta)
    if m:
        f['data_vencimento'] = f.get('data_vencimento') or _data(m.group(1))
        f['_total_conta'] = candidatos_valor(m.group(2))
    m = re.search(r'REFER\S*\s*\S{0,3}\s*(\d{2})\s*/\s*(\d{4})', conta, re.I)
    if m and not f.get('competencia') and 1 <= int(m.group(1)) <= 12:
        f['competencia'] = f"{m.group(2)}-{m.group(1)}"


def _danf3e_nativo(pdf_path):
    """O PDF é um DANF3E gerado (texto embutido limpo, não um scan com OCR do scanner)?"""
    import fitz
    with fitz.open(pdf_path) as d:
        txt = d[0].get_text() if d.page_count else ''
    up = txt.upper()
    return (len(txt) > 800 and ('DOCUMENTO AUXILIAR DA NOTA FISCAL' in up or 'CHAVE DE ACESSO' in up)
            and bool(re.search(r'\d{2}/\d{2}/\d{4}', txt)) and bool(re.search(r'kWh', txt)))


_RE_CANHOTO = re.compile(r'(\d{2}/\d{2}/\d{4})\s+(20\d{11})\s+(JAN|FEV|MAR|ABR|MAI|JUN|JUL|AGO|SET|OUT|NOV|DEZ)\s*/\s*(\d{4})'
                         r'\s+(\d{2}/\d{2}/\d{4})\s+R\s?\$\s*(\S+)', re.I)
_MESES = {m: f"{i:02d}" for i, m in enumerate(('JAN', 'FEV', 'MAR', 'ABR', 'MAI', 'JUN', 'JUL', 'AGO', 'SET', 'OUT',
                                                'NOV', 'DEZ'), 1)}


def _danf3e_escaneado(doc, pp, palavras, dicas=None):
    """DANF3E digitalizado (2022–2025). Esses scans vêm em ~150 dpi: o cabeçalho, o canhoto e o
    quadro de tributos são legíveis, mas a tabela de itens (fonte de ~5 pt) não é — o OCR não
    a recupera com confiança. Sai só o que é seguro (total, datas, UC, nota, tributos, demanda),
    com `_somente_cabecalho` e aviso para completar os itens (ex.: pelo borderô)."""
    p1 = _texto(palavras)
    resto = '\n'.join(_tesseract(doc, i) for i in range(doc.paginas) if i != pp)
    txt = p1 + '\n' + resto
    canhoto = _abaixo(doc, pp, palavras, r'REFER\S*', faixa=(0.55, 1.0), altura=80, variante='rgb')
    f = {}
    totais = Counter()
    for fonte in (canhoto, txt):
        m = _RE_CANHOTO.search(fonte or '')
        if m:
            f.setdefault('data_emissao', _data(m.group(1)))
            f.setdefault('numero_fatura', m.group(2))
            f.setdefault('competencia', f"{m.group(4)}-{_MESES[m.group(3).upper()]}")
            f.setdefault('data_vencimento', _data(m.group(5)))
            for i, v in enumerate(candidatos_valor(m.group(6))):
                totais[round(v * 100)] += 3 if i == 0 else 1
    m = re.search(r'NOTA\s+FISCAL\s+N\S{0,2}\s*(\d{6,9})\s*-\s*S[ÉE]RIE\s*(\w{1,3})\s*/\s*DATA\s+DE\s+EMISS\S*\s*(\d{2}/\d{2}/\d{4})', txt, re.I)
    if m:
        f['numero_nf'], f['serie_nf'] = m.group(1), m.group(2).replace('O', '0')
        f.setdefault('data_emissao', _data(m.group(3)))
    f['id_uc'] = (_get(r'N\S?\s*CONTROLE:?[^\n]*\n\s*0*(\d{7,10})\b', txt) or _get(r'\bUC\s*:?\s*(\d{7,10})', txt))
    if dicas and dicas.get('valor_total') is not None:
        totais[round(dicas['valor_total'] * 100)] += 10
    total = totais.most_common(1)[0][0] / 100 if totais else None
    m = re.search(r'(\d{2}/\d{2}/\d{4})\D{1,12}(\d{2}/\d{2}/\d{4})\D{1,12}(\d{1,2})\D{1,12}(\d{2}/\d{2}/\d{4})', txt)
    if m:
        f['data_leitura_anterior'], f['data_leitura_atual'] = _data(m.group(1)), _data(m.group(2))
        f['numero_dias_leitura'], f['data_proxima_leitura'] = int(m.group(3)), _data(m.group(4))
    classif = _get(r'Classifica\S*:\s*([A-Z][^\n|]*?)(?:\s{2,}|\s+Tipo\b|\s+TRIF|$)', txt, flags=re.I | re.M)
    impostos = []
    for nome, pat in (('PIS/PASEP', r'PIS/?PASEP\s+([\d.,]+)\s+([\d.,]+)\s*%\s+([\d.,]+)'),
                      ('ICMS', r'\bICMS\s+([\d.,]+)\s+(\d{1,2}(?:[.,]\d+)?)\s*%\s+([\d.,]+)'),
                      ('COFINS', r'COFINS\s+([\d.,]+)\s+([\d.,]+)\s*%\s+([\d.,]+)')):
        m = re.search(pat, txt, re.I)
        if not m:
            continue
        aliq = numero(m.group(2))
        if aliq and aliq > 30 and ',' not in m.group(2):            # '33537' = 3,3537
            aliq = float(m.group(2)[0] + '.' + m.group(2)[1:])
        base = next(iter(candidatos_valor(m.group(1))), None)
        val = next((v for v in candidatos_valor(m.group(3))
                    if base and aliq and abs(round(base * aliq / 100, 2) - v) <= 0.02), None)
        if base and aliq and val is not None:
            impostos.append({'Tributo': nome, 'Base (R$)': base, 'Aliquota (%)': f"{aliq}%", 'Valor (R$)': val})
    uc, comp = f.get('id_uc'), f.get('competencia')
    numero_fat = f.get('numero_fatura')
    id_fatura = (f"EQUATORIAL_{numero_fat}" if numero_fat else
                 f"EQUATORIAL_{uc}_{comp.replace('-', '')}" if uc and comp else
                 f"EQUATORIAL_{os.path.splitext(doc.nome)[0]}")
    consumo_medio = numero(_get(r'Consumo\s+M[ée]dio\s+Di[áa]rio\s*\(kWh\)\s*:?\s*([\d.,]+)', txt))
    avisos = ["DANF3E digitalizado em baixa resolução: itens e medição não extraídos (só cabeçalho, total e tributos)"]
    if consumo_medio and f.get('numero_dias_leitura'):
        avisos.append(f"consumo médio diário {consumo_medio} kWh × {f['numero_dias_leitura']} dias")
    for k, rotulo in (('competencia', 'competência'), ('data_vencimento', 'vencimento'), ('id_uc', 'UC')):
        if not f.get(k):
            avisos.append(f"{rotulo} ilegível")
    if total is None:
        avisos.append("total da fatura ilegível no OCR")
    fat = {
        'id_fatura': id_fatura, 'numero_fatura': numero_fat, 'arquivo_pdf': doc.nome, 'fornecedor': 'EQUATORIAL',
        'id_uc': uc, 'data_emissao': f.get('data_emissao'), 'competencia': comp,
        'data_vencimento': f.get('data_vencimento'), 'valor_total_r$': total,
        'numero_nf': f.get('numero_nf'), 'serie_nf': f.get('serie_nf'), 'cfop': '5258', 'chave_acesso_nfe': None,
        'protocolo_autorizacao': None, 'data_hora_protocolo': None, 'classificacao_tarifaria': classif,
        'tipo_fornecimento': _get(r'(TRIF[ÁA]SICO|MONOF[ÁA]SICO|BIF[ÁA]SICO)', txt), 'tensao_nominal_v': None,
        'tensao_min_v': None, 'tensao_max_v': None,
        'demanda_contratada_kw': numero(_get(r'DEMANDA\s*-\s*kW\s+(\d{1,4}(?:,\d+)?)\b', txt)),
        'demanda_geracao_contratada_kw': None, 'perdas_transformacao_pct': None, 'scee_geracao_ciclo': None,
        'scee_saldo_kwh_total': None, 'scee_saldo_kwh_P': None, 'scee_saldo_kwh_FP': None, 'scee_saldo_kwh_HR': None,
        'data_leitura_anterior': f.get('data_leitura_anterior'), 'data_leitura_atual': f.get('data_leitura_atual'),
        'numero_dias_leitura': f.get('numero_dias_leitura'), 'data_proxima_leitura': f.get('data_proxima_leitura'),
        'mensagens_importantes': "[extrator] " + "; ".join(avisos) + " — conferir no PDF",
        'extraido_por_ocr': True,
    }
    cli = {'id_uc': uc, 'razao_social': _razao(txt), 'cnpj': _cnpj(txt), 'cep': _get(r'CEP:?\s*(\d{8})\b', txt),
           'municipio': _municipio(txt), 'uf': 'GO'}
    resultado = {'fatura': fat, 'unidade_consumidora': cli, 'itens_fatura': [], 'impostos': impostos, 'medicao': [],
                 '_somente_cabecalho': True}
    for r in impostos:
        r['id_fatura'] = id_fatura
    from .equatorial import carimbar_id_uc_competencia
    carimbar_id_uc_competencia(resultado, uc or f"NULO_{id_fatura}", comp)
    resultado['_conferencia'] = {'layout': 'DANF3E_ESCANEADO', 'fecha': False, 'soma_itens': 0.0, 'total': total,
                                 'avisos': avisos}
    return resultado


def processar_pdf(pdf_path, dicas=None):
    """Lê uma fatura ENEL antiga (OCR). `dicas` (opcional, do borderô):
    {'valor_total': 778.96} — reforça o total quando o da própria fatura está ilegível."""
    from . import ocr
    if not ocr.configurar_ocr():
        raise RuntimeError(f"O PDF '{os.path.basename(pdf_path)}' é digitalizado e precisa de OCR, "
                           "mas o Tesseract não foi encontrado.")
    if _danf3e_nativo(pdf_path):                     # DANF3E com texto de verdade: leitor da Equatorial
        from . import equatorial
        rs = equatorial.processar_pdf_multi(pdf_path)
        if all(r.get('itens_fatura') and (r.get('fatura') or {}).get('valor_total_r$') for r in rs):
            return rs
        # texto embutido era o OCR do scanner (lixo): segue pela leitura própria
    doc = _Doc(pdf_path)
    pp, palavras, lay = _pagina_principal(doc)
    p1 = _texto(palavras)
    if lay == 'DANF3E':
        return _danf3e_escaneado(doc, pp, palavras, dicas)
    if lay is None:
        raise ValueError(f"'{doc.nome}': layout de fatura ENEL não reconhecido (texto ilegível ou outro documento).")
    resto = '\n'.join(_tesseract(doc, i) for i in range(doc.paginas) if i != pp)
    f = _cabecalho(lay, p1, resto)
    if lay == 'B_2020':
        _aplicar_extras_b2020(f, _extras_b2020(doc, pp, palavras))
    else:
        f['_total_recorte'] = _total_recortado(doc, pp, palavras)

    totais = Counter()
    for k, peso in (('_total', 3), ('_total_recorte', 3), ('_total_canhoto', 3), ('_total_conta', 3)):
        for i, v in enumerate(f.get(k) or []):
            if 0 < v < 10_000_000:                     # descarta 'totais' que são código de barras
                totais[round(v * 100)] += peso if i == 0 else 1
    if dicas and dicas.get('valor_total') is not None:
        totais[round(dicas['valor_total'] * 100)] += 10
    bases = _bases(lay, p1, f)

    for extra in (False, True):
        leituras, cols = _ler_itens(doc, pp, palavras, lay, extra=extra)
        grupos = _juntar(leituras, cols)
        tot, desvio = _reconciliar(grupos, len(leituras), totais.most_common(8), bases.most_common(3))
        if tot is not None and desvio == 0:
            break

    itens = []
    for g in grupos:
        if g.get('valor') is None:
            continue
        forn = g['tipo'] == 'FORNECIMENTO'
        if forn and g.get('tarifa') and g.get('qtd'):
            v = abs(g['valor']) / 100
            for fator in (1, 10, 100, 1000):           # vírgula perdida na quantidade ('205' = 2,05)
                if abs(g['qtd'] / fator * g['tarifa'] - v) <= max(0.03, v * 0.005):
                    g['qtd'] = round(g['qtd'] / fator, 4)
                    break
        itens.append({'item': g['nome'], 'tipo': g['tipo'], 'unidade': g['unidade'] if forn else None,
                      'quantidade': g['qtd'] if forn else None,
                      'preco_unitario_com_tributos_r$': g['tarifa'] if forn else None,
                      'valor_r$': round(g['valor'] / 100, 2), 'pis_cofins': None, 'base_calc_icms_r$': None,
                      'aliquota_icms_r$': None, 'icms': None, 'tarifa_unitaria_r$': None})
    soma = round(sum(i['valor_r$'] for i in itens), 2)
    if tot is not None:
        total = tot / 100
    else:
        total = totais.most_common(1)[0][0] / 100 if totais else None
    base_cent = round(sum(i['valor_r$'] for i in itens if i['tipo'] == 'FORNECIMENTO') * 100) if itens else None

    if lay == 'GRUPO_A':
        dem = next((i['quantidade'] for i in itens if i['item'] == 'DEMANDA' and i['quantidade']), None)
        if dem and f.get('demanda_contratada_kw') and f['demanda_contratada_kw'] != dem \
                and str(int(f['demanda_contratada_kw'])).endswith(str(int(dem))):
            f['demanda_contratada_kw'] = dem              # 'DEMANDA 275': o OCR grudou lixo no 75
        classif = f"A {f.get('grupo') or 'A4'} PODER PÚBLICO" + (f" {f['estrutura']}" if f.get('estrutura') else '')
        tipo_forn = 'TRIFÁSICO'
        cons = {(_posto(i['item']) or ''): i['quantidade'] for i in itens if i['item'].startswith('CONSUMO')}
        medicao = _medicao_grupo_a(resto, f.get('perdas_transformacao_pct'), f.get('medidor'), cons)
    else:
        classif = (f"B {f.get('subgrupo') or 'B3'} PODER PÚBLICO" + (" - FEDERAL" if 'FEDERAL' in p1.upper() else '')
                   + " CONVENCIONAL")
        tipo_forn = f.get('tipo_fornecimento')
        consumo = next((i['quantidade'] for i in itens if i['item'].startswith('CONSUMO') and i['quantidade']), None)
        la, lb = numero(f.get('leitura_atual')), numero(f.get('leitura_anterior'))
        medicao = [{'Grandezas': 'ENERGIA ATIVA - KWH', 'Postos horarios': 'ÚNICO',
                    'Leitura Anterior': int(lb) if lb is not None else None,
                    'Leitura Atual': int(la) if la is not None else None, 'Const Medidor': 1.0,
                    'Consumo kWh': consumo, 'Medidor': f.get('medidor')}] if consumo else []

    # identificador estável: UC + competência (o número da conta, lido por OCR, pode vir com dígito trocado)
    numero_fat, nf, uc, comp = f.get('numero_fatura'), f.get('numero_nf'), f.get('id_uc'), f.get('competencia')
    if uc and comp:
        id_fatura = f"{FORNECEDOR}_{uc}_{comp.replace('-', '')}"
    elif numero_fat or nf:
        id_fatura = f"{FORNECEDOR}_{numero_fat or 'NF' + nf}"
    else:
        id_fatura = f"{FORNECEDOR}_{os.path.splitext(doc.nome)[0]}"

    avisos = [f"valor de '{g['nome']}' deduzido do total (ilegível no OCR)" for g in grupos if g.get('pela_diferenca')]
    if total is None:
        avisos.append("total da fatura ilegível no OCR")
    elif abs(soma - total) > 0.005:
        avisos.append(f"soma dos itens lidos por OCR ({soma:.2f}) ≠ total ({total:.2f})")
    for k, rotulo in (('competencia', 'competência'), ('data_vencimento', 'vencimento'), ('id_uc', 'UC')):
        if not f.get(k):
            avisos.append(f"{rotulo} ilegível")
    fat = {
        'id_fatura': id_fatura, 'numero_fatura': numero_fat or nf, 'arquivo_pdf': doc.nome, 'fornecedor': FORNECEDOR,
        'id_uc': uc, 'data_emissao': f.get('data_emissao'), 'competencia': comp,
        'data_vencimento': f.get('data_vencimento'), 'valor_total_r$': total,
        'numero_nf': nf, 'serie_nf': f.get('serie_nf'), 'cfop': None, 'chave_acesso_nfe': None,
        'protocolo_autorizacao': None, 'data_hora_protocolo': None, 'classificacao_tarifaria': classif,
        'tipo_fornecimento': tipo_forn, 'tensao_nominal_v': None, 'tensao_min_v': None, 'tensao_max_v': None,
        'demanda_contratada_kw': f.get('demanda_contratada_kw'), 'demanda_geracao_contratada_kw': None,
        'perdas_transformacao_pct': f.get('perdas_transformacao_pct'), 'scee_geracao_ciclo': None,
        'scee_saldo_kwh_total': None, 'scee_saldo_kwh_P': None, 'scee_saldo_kwh_FP': None, 'scee_saldo_kwh_HR': None,
        'data_leitura_anterior': f.get('data_leitura_anterior'), 'data_leitura_atual': f.get('data_leitura_atual'),
        'numero_dias_leitura': int(f['numero_dias_leitura']) if f.get('numero_dias_leitura') else None,
        'data_proxima_leitura': f.get('data_proxima_leitura'),
        'mensagens_importantes': ("[extrator] " + "; ".join(avisos) + " — conferir no PDF") if avisos else None,
        'extraido_por_ocr': True,
    }
    cli = {'id_uc': uc, 'razao_social': _razao(p1), 'cnpj': _cnpj(p1),
           'cep': _get(r'CEP:?\s*(\d{8})\b', p1), 'municipio': _municipio(p1), 'uf': 'GO'}
    resultado = {'fatura': fat, 'unidade_consumidora': cli, 'itens_fatura': itens,
                 'impostos': _tributos(lay, p1, f, base_cent), 'medicao': medicao}
    for aba in ('itens_fatura', 'impostos', 'medicao'):
        for r in resultado[aba]:
            r['id_fatura'] = id_fatura
    from .equatorial import carimbar_id_uc_competencia
    carimbar_id_uc_competencia(resultado, uc or f"NULO_{id_fatura}", comp)
    resultado['_conferencia'] = {'layout': lay, 'fecha': total is not None and abs(soma - total) <= 0.005,
                                 'soma_itens': soma, 'total': total, 'avisos': avisos}
    return resultado


def _razao(txt):
    for pat in (r'(INSTITUTO NACIONAL DE METROLOGIA,?\s*QUALIDADE E TECNOLOGIA)', r'(SUPERINTEND\S+\s+REGIONAL\s+DO\s+\S+)'):
        m = re.search(pat, txt, re.I)
        if m:
            return re.sub(r'\s+', ' ', m.group(1)).upper()
    return None


def _cnpj(txt):
    for m in re.finditer(r'CNPJ\s*/?\s*(?:CPF)?:?\s*(\d{2}\.?\d{3}\.?\d{3}[./]?\d{4}-?\d{2})', txt, re.I):
        d = re.sub(r'\D', '', m.group(1))
        if len(d) == 14 and d != '01543032000104':      # o da própria distribuidora não
            return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"
    return None


def _municipio(txt):
    m = re.search(r'CEP:?\s*\d{8}\s+([A-ZÀ-Ú][A-ZÀ-Ú ]+?)\s*-?\s*GO\b', txt)
    return m.group(1).strip() if m else None
