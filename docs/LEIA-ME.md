# Versão web (GitHub Pages)

Roda o **mesmo núcleo de extração** do aplicativo desktop
(`src/faturas_app/core`) dentro do navegador, com
[Pyodide](https://pyodide.org) — CPython compilado para WebAssembly.

Os PDFs **não saem da máquina de quem usa**: são lidos na própria aba e a
planilha é montada na memória do navegador. Não há servidor.

## Como publicar

1. `python build/sync_web.py` — copia `src/faturas_app` para `docs/py/` e
   regenera `docs/py/manifesto.json`. **Rode sempre que mexer no núcleo**,
   senão a versão web fica atrasada em relação ao desktop.
2. Commit e push.
3. No GitHub: **Settings → Pages → Source: `Deploy from a branch`**, branch da
   sua escolha, pasta **`/docs`**. (Passo único, feito uma vez.)

## O que NÃO funciona nesta versão

| Recurso | Motivo |
|---|---|
| Faturas CHESP **escaneadas** | Precisam de OCR (Tesseract, binário nativo). Sem build WebAssembly. São detectadas e reportadas, não processadas. |
| **Borderôs** | `core/borderos.py` lê por coordenadas com PyMuPDF, que não tem build WebAssembly. |
| Interface do desktop | CustomTkinter/Tkinter não roda no navegador — a interface web é própria (`index.html` + `app.js`). |

Faturas CHESP **com texto** funcionam normalmente; só as escaneadas (~22% do
acervo do TJGO) dependem de OCR.

## Detalhe de instalação que não é óbvio

`pdfplumber` é instalado com `deps: false`. Ele declara `pillow>=12.2.0`, mais
nova que a Pillow embutida no Pyodide, e com as dependências ligadas o micropip
recusa a instalação inteira. A extração de **texto** usa apenas o
`pdfminer.six` (puro Python, instala normalmente); a Pillow do pdfplumber serve
para rasterizar página, coisa que este app não faz.
