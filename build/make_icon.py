r"""
Gera build/app.ico — ícone do app: documento (fatura) com raio de energia,
sobre quadrado arredondado azul (tema do CustomTkinter). Multi-resolução.

Uso:  .venv\Scripts\python.exe build\make_icon.py
"""
import os

from PIL import Image, ImageDraw

SIZE = 256
AZUL = (31, 106, 165, 255)        # azul CustomTkinter
AZUL_ESC = (20, 71, 110, 255)
BRANCO = (255, 255, 255, 255)
CINZA = (170, 178, 188, 255)
AMBAR = (245, 183, 49, 255)


def rounded(draw, box, r, fill):
    draw.rounded_rectangle(box, radius=r, fill=fill)


def gerar(size=SIZE):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = size / 256.0

    # fundo arredondado azul (com leve borda mais escura)
    rounded(d, [4 * s, 4 * s, 252 * s, 252 * s], 52 * s, AZUL_ESC)
    rounded(d, [10 * s, 10 * s, 246 * s, 246 * s], 48 * s, AZUL)

    # documento branco com canto dobrado
    x0, y0, x1, y1 = 64 * s, 50 * s, 192 * s, 210 * s
    dobra = 30 * s
    corpo = [
        (x0, y0), (x1 - dobra, y0), (x1, y0 + dobra),
        (x1, y1), (x0, y1),
    ]
    d.polygon(corpo, fill=BRANCO)
    # canto dobrado (triângulo sombreado)
    d.polygon([(x1 - dobra, y0), (x1 - dobra, y0 + dobra), (x1, y0 + dobra)], fill=CINZA)

    # linhas de texto (campos da fatura)
    for i in range(4):
        ly = (78 + i * 20) * s
        lw = (x1 - 22 * s) if i % 2 == 0 else (x1 - 48 * s)
        d.rounded_rectangle([x0 + 16 * s, ly, lw, ly + 7 * s],
                            radius=3 * s, fill=CINZA)

    # raio de energia (âmbar) sobre o documento
    raio = [
        (150 * s, 150 * s), (120 * s, 196 * s), (140 * s, 196 * s),
        (118 * s, 232 * s), (172 * s, 178 * s), (146 * s, 178 * s),
        (168 * s, 150 * s),
    ]
    # contorno branco para destacar
    d.polygon([(px + 0, py) for px, py in raio], fill=AMBAR)
    d.line(raio + [raio[0]], fill=BRANCO, width=max(1, int(3 * s)), joint="curve")
    return img


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    base = gerar(SIZE)
    saidas = [base.resize((n, n), Image.LANCZOS) for n in (256, 128, 64, 48, 32, 16)]
    ico = os.path.join(here, "app.ico")
    base.save(ico, sizes=[(im.width, im.height) for im in saidas])
    # também um PNG para o instalador / atalhos, se útil
    base.save(os.path.join(here, "app.png"))
    print("OK ->", ico)


if __name__ == "__main__":
    main()
