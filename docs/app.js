/*
 * Versão web do Processador de Faturas de Energia.
 *
 * Roda o MESMO núcleo de extração do app desktop (`faturas_app.core`) dentro do
 * navegador, via Pyodide (CPython compilado para WebAssembly). Nada é enviado
 * para servidor nenhum: os PDFs são lidos no próprio navegador e a planilha é
 * gerada na memória da aba.
 *
 * Pontos que exigiram cuidado:
 *
 *  - `pdfplumber` é instalado com `deps: false`. Ele declara
 *    `pillow>=12.2.0`, versão mais nova que a Pillow embutida no Pyodide, e com
 *    as dependências ligadas o micropip recusa a instalação inteira. A extração
 *    de TEXTO usa só o pdfminer.six (puro Python, esse instala normal); a
 *    Pillow do pdfplumber serve para rasterizar página, que este app não faz.
 *  - `gui/` e `core/borderos.py` NÃO são publicados (ver build/sync_web.py):
 *    Tkinter não roda no navegador e o PyMuPDF não tem build WebAssembly.
 *  - CHESP escaneada precisa de OCR (Tesseract, binário nativo): o app detecta
 *    e reporta em vez de fingir que processou.
 */
"use strict";

const $ = (id) => document.getElementById(id);
const elLog = $("log"), elProg = $("prog"), elLista = $("lista"),
      elBtn = $("btn"), elBaixar = $("baixar"), elResumo = $("resumo"),
      elZona = $("zona"), elArquivos = $("arquivos"), elForn = $("forn");

let py = null;
let selecionados = [];
let xlsxBytes = null;

function log(msg, classe) {
  const linha = classe ? `[${classe}] ${msg}` : msg;
  elLog.textContent += "\n" + linha;
  elLog.scrollTop = elLog.scrollHeight;
}
function progresso(feito, total) {
  elProg.style.width = total ? `${Math.round((feito / total) * 100)}%` : "0%";
}

// ── seleção de arquivos ──────────────────────────────────────────────────────
elZona.addEventListener("click", () => elArquivos.click());
elZona.addEventListener("dragover", (e) => { e.preventDefault(); elZona.classList.add("on"); });
elZona.addEventListener("dragleave", () => elZona.classList.remove("on"));
elZona.addEventListener("drop", (e) => {
  e.preventDefault(); elZona.classList.remove("on");
  adicionar([...e.dataTransfer.files].filter((f) => f.name.toLowerCase().endsWith(".pdf")));
});
elArquivos.addEventListener("change", () => adicionar([...elArquivos.files]));

function adicionar(arquivos) {
  const vistos = new Set(selecionados.map((f) => f.name + f.size));
  for (const f of arquivos) {
    if (!vistos.has(f.name + f.size)) { selecionados.push(f); vistos.add(f.name + f.size); }
  }
  elLista.innerHTML = selecionados
    .map((f) => `<div>${f.name} <span style="opacity:.6">(${(f.size / 1024).toFixed(0)} KB)</span></div>`)
    .join("");
  elResumo.textContent = `${selecionados.length} PDF(s) selecionado(s)`;
  atualizarBotao();
}
function atualizarBotao() {
  elBtn.disabled = !(py && selecionados.length);
  if (py) elBtn.textContent = `▶ Processar ${selecionados.length || ""} PDF(s)`.replace("  ", " ");
}

// ── ambiente Python ──────────────────────────────────────────────────────────
async function iniciar() {
  try {
    log("carregando Pyodide…");
    py = await loadPyodide();
    await py.loadPackage(["micropip", "pandas"]);
    const micropip = py.pyimport("micropip");
    log("instalando pdfminer.six e openpyxl…");
    await micropip.install(["pdfminer.six", "openpyxl"]);
    // ver comentário no topo: sem `deps:false` o micropip recusa por causa da Pillow
    log("instalando pdfplumber…");
    await micropip.install.callKwargs("pdfplumber", { deps: false });

    log("publicando o núcleo do app…");
    const manifesto = await (await fetch("py/manifesto.json")).json();
    py.FS.mkdir("/app");
    const criados = new Set();
    for (const rel of manifesto) {
      const partes = ("faturas_app/" + rel).split("/");
      let atual = "/app";
      for (const p of partes.slice(0, -1)) {
        atual += "/" + p;
        if (!criados.has(atual)) { try { py.FS.mkdir(atual); } catch (_) {} criados.add(atual); }
      }
      const r = await fetch("py/faturas_app/" + rel);
      if (!r.ok) { log(`não consegui baixar ${rel}`, "AVISO"); continue; }
      py.FS.writeFile("/app/faturas_app/" + rel, new Uint8Array(await r.arrayBuffer()));
    }
    // HOME próprio: equivalencias/hardcodes/dicionário gravam em %APPDATA% ou ~
    py.FS.mkdir("/home/web");
    py.runPython(`
import os, sys
os.environ["APPDATA"] = "/home/web"
sys.path.insert(0, "/app")
from faturas_app.core import equatorial, chesp, dataset, derivados, excel_io, glossario
from faturas_app.core.profile import Perfil
`);
    log("pronto — o motor está carregado.", "OK");
    elLog.textContent = elLog.textContent.replace(
      "Preparando o ambiente Python (isso leva alguns segundos na primeira vez)…",
      "Ambiente pronto.");
    atualizarBotao();
  } catch (e) {
    log("falha ao preparar o ambiente: " + String(e), "ERRO");
    elBtn.textContent = "Falhou ao carregar";
  }
}

// ── processamento ────────────────────────────────────────────────────────────
elBtn.addEventListener("click", async () => {
  elBtn.disabled = true; elBaixar.disabled = true; xlsxBytes = null;
  const fornecedor = elForn.value;
  log(`\n=== processando ${selecionados.length} PDF(s) como ${fornecedor} ===`);

  py.runPython(`
from faturas_app.core import dataset
_ds = dataset.Dataset()
_erros = []
`);
  let ok = 0;
  for (let i = 0; i < selecionados.length; i++) {
    const f = selecionados[i];
    progresso(i, selecionados.length);
    elResumo.textContent = `${i + 1}/${selecionados.length} — ${f.name}`;
    try {
      py.FS.writeFile("/entrada.pdf", new Uint8Array(await f.arrayBuffer()));
      const erro = py.runPython(`
import traceback
from faturas_app.core import equatorial, chesp
try:
    if ${JSON.stringify(fornecedor)} == "EQUATORIAL":
        _rs = equatorial.processar_pdf_multi("/entrada.pdf")
    else:
        _rs = [chesp.processar_pdf("/entrada.pdf")]
    for _r in (_rs if isinstance(_rs, list) else [_rs]):
        _ds.adicionar_resultado(_r)
    _saida = ""
except chesp.OCRIndisponivelError as e:
    _saida = "PRECISA DE OCR: " + str(e)
except Exception as e:
    _saida = f"{type(e).__name__}: {e}"
_saida
`);
      if (erro) { log(`${f.name}: ${erro}`, "ERRO"); }
      else { ok++; }
    } catch (e) {
      log(`${f.name}: ${String(e)}`, "ERRO");
    }
    // devolve o controle ao navegador para a barra andar
    await new Promise((r) => setTimeout(r, 0));
  }
  progresso(selecionados.length, selecionados.length);
  log(`${ok} de ${selecionados.length} fatura(s) processada(s).`, ok ? "OK" : "ERRO");

  if (!ok) {
    elResumo.textContent = "nenhuma fatura processada";
    elBtn.disabled = false;
    return;
  }

  log("consolidando e gerando a planilha…");
  const resumo = py.runPython(`
import json, traceback
try:
    from faturas_app.core import derivados, excel_io, glossario, links
    from faturas_app.core.profile import Perfil
    _dfs = _ds.to_dataframes()
    _dfs["fatura"] = links.aplicar_link(_dfs["fatura"], links.MODO_LOCAL, None)
    derivados.aplicar(_dfs)
    _perfil = Perfil.padrao_de_dataframes(_dfs)
    _display = glossario.garantir_glossario(_perfil.aplicar(_dfs))
    excel_io.escrever_workbook(_display, _perfil.to_meta(), "/saida.xlsx")
    _out = json.dumps({"abas": {a: len(d) for a, d in _display.items()},
                       "faturas": _ds.total_faturas()}, ensure_ascii=False)
except Exception:
    _out = "ERRO:" + traceback.format_exc()
_out
`);
  if (resumo.startsWith("ERRO:")) {
    log(resumo, "ERRO");
    elBtn.disabled = false;
    return;
  }
  const info = JSON.parse(resumo);
  log(`planilha pronta — ${info.faturas} fatura(s):`, "OK");
  for (const [aba, n] of Object.entries(info.abas)) log(`   ${aba}: ${n} linha(s)`);

  xlsxBytes = py.FS.readFile("/saida.xlsx");
  elBaixar.disabled = false;
  elResumo.textContent = `${info.faturas} fatura(s) — planilha pronta`;
  elBtn.disabled = false;
});

elBaixar.addEventListener("click", () => {
  if (!xlsxBytes) return;
  const blob = new Blob([xlsxBytes], {
    type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "faturas_energia.xlsx";
  a.click();
  URL.revokeObjectURL(a.href);
});

iniciar();
