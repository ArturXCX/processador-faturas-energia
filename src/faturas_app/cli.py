"""
Modo LINHA DE COMANDO: processa pastas de PDFs sem abrir a interface.

    faturas-cli --pasta <dir>[=EQUATORIAL|CHESP] [--pasta ...] [--subpastas]
                --saida <planilha.xlsx> [--csv <dir>] [--cache <dir>]
                [--paralelo N] [--mapa-uc <json|xlsx>] [--link busca_drive|local|template]

O mesmo núcleo da interface (controller → Dataset → derivados → hardcodes →
Perfil → excel_io), com três diferenças pensadas para rotina/automação:

  - PARALELO: cada PDF é independente, então um pool de processos lê vários
    ao mesmo tempo (o OCR das CHESP escaneadas e a leitura de PDFs em disco de
    rede são o gargalo). A ordem de entrada no lote é a da listagem, como na
    interface — o resultado não depende de quem terminou primeiro.
  - CACHE por PDF (JSON): um PDF já processado não é lido de novo enquanto o
    arquivo (tamanho/mtime) e a versão do app forem os mesmos. Jogar PDFs
    novos na pasta e rodar de novo só processa os novos.
  - CSV por aba (opcional), para o Excel com Power Query "da pasta"
    consolidar sem abrir o app.

A fornecedora de cada pasta vem depois do '=' ou, na falta dele, do nome de
alguma pasta do caminho ('chesp' / 'equatorial').
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import hashlib
import json
import os
import re
import sys
import time
import unicodedata

from . import __version__

FORNECEDORES = ("EQUATORIAL", "CHESP")


# ──────────────────────────────────────────────────────────────────────────────
# Entrada
# ──────────────────────────────────────────────────────────────────────────────
def _inferir_fornecedor(caminho: str) -> str | None:
    partes = [p.lower() for p in os.path.normpath(caminho).split(os.sep)]
    for p in reversed(partes):
        if "chesp" in p:
            return "CHESP"
        if "equatorial" in p or "enel" in p or "celg" in p:
            return "EQUATORIAL"
    return None


def _listar(spec: str, subpastas: bool) -> list[tuple[str, str]]:
    """'dir' ou 'dir=FORNECEDOR' → [(pdf, fornecedor)]."""
    from .core import controller
    pasta, _, forn = spec.rpartition("=")
    if not pasta or forn.upper() not in FORNECEDORES:
        pasta, forn = spec, ""
    pasta = os.path.abspath(pasta)
    if not os.path.isdir(pasta):
        raise SystemExit(f"Pasta não encontrada: {pasta}")
    saida = []
    sem_forn = []
    for pdf in controller.listar_pdfs(pasta, subpastas):
        f = forn.upper() or _inferir_fornecedor(pdf)
        if f is None:
            sem_forn.append(pdf)
            continue
        saida.append((pdf, f))
    if sem_forn:
        raise SystemExit(
            f"Não sei a fornecedora de {len(sem_forn)} PDF(s) em '{pasta}' (ex.: "
            f"{os.path.basename(sem_forn[0])}). Use --pasta \"{pasta}=EQUATORIAL\" "
            f"ou =CHESP, ou coloque os PDFs em subpastas chamadas equatorial/chesp.")
    return saida


# ──────────────────────────────────────────────────────────────────────────────
# Processamento de UM PDF (roda nos processos filhos)
# ──────────────────────────────────────────────────────────────────────────────
def _chave_cache(pdf: str) -> str:
    st = os.stat(pdf)
    bruto = f"{__version__}|{os.path.abspath(pdf).lower()}|{st.st_size}|{st.st_mtime_ns}"
    return hashlib.sha1(bruto.encode("utf-8")).hexdigest()


def _processar_um(args):
    pdf, forn, cache_dir = args
    from .core import controller
    try:
        fp = os.path.join(cache_dir, _chave_cache(pdf) + ".json") if cache_dir else None
        if fp and os.path.isfile(fp):
            with open(fp, "r", encoding="utf-8") as f:
                return pdf, forn, json.load(f), None, True
        r = controller.PROCESSADORES[forn](pdf)
        resultados = r if isinstance(r, list) else [r]
        if fp:
            tmp = fp + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(resultados, f, ensure_ascii=False)
            os.replace(tmp, fp)
        return pdf, forn, resultados, None, False
    except Exception as e:  # noqa: BLE001 — registrado no lote, o resto segue
        return pdf, forn, None, f"{type(e).__name__}: {e}", False


# ──────────────────────────────────────────────────────────────────────────────
# Mapa de UCs sem interface
# ──────────────────────────────────────────────────────────────────────────────
def _slug(nome: str) -> str:
    s = unicodedata.normalize("NFKD", str(nome)).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")
    return s or "campo"


def importar_mapa_uc(caminho: str, usar_medidor: bool = True, extras: bool = True,
                     log=print) -> dict:
    """
    Importa o mapa de UCs como a aba Parâmetros faria, mas sem perguntas:
    chave = 'id_uc' (ou o campo que mais parece identificador), identificadores
    alternativos sugeridos ('UC VELHA'…) todos marcados, itens do template
    casados por nome exato ou por palavra-chave, e — se `extras` — todos os
    demais campos viram colunas extras com nome normalizado.
    """
    from .core import dicionario_uc
    analise = dicionario_uc.analisar_arquivo(caminho)
    mapeamento = dict(analise.get("sugeridos") or {})
    ids_extras = list(analise.get("ids_extras_sugeridos") or [])
    usados = set(analise["auto"].values()) | set(mapeamento.values()) | set(ids_extras) | {analise["chave"]}
    ext = {c: _slug(c) for c in analise["sobrando"] if c not in usados} if extras else {}
    registros, cols_extras = dicionario_uc.aplicar_mapeamento(
        analise, mapeamento, ext, chave=analise["chave"], ids_extras=ids_extras)
    if not registros:
        raise SystemExit(f"Nenhum registro com identificador de UC em {caminho}.")
    meta = dicionario_uc.salvar_mapa(registros, cols_extras)
    dicionario_uc.definir_usar_medidor(usar_medidor)
    log(f"Mapa de UCs importado de {os.path.basename(caminho)}: {meta['total_ucs']} UC(s); "
        f"chave '{analise['chave']}'"
        + (f" + alternativos {ids_extras}" if ids_extras else "")
        + f"; {len(meta['colunas'])} coluna(s) de cadastro.")
    for a in analise.get("avisos", []):
        log(f"  aviso: {a}")
    for a in dicionario_uc.avisos()[:5]:
        log(f"  aviso: {a}")
    return meta


# ──────────────────────────────────────────────────────────────────────────────
# Lote
# ──────────────────────────────────────────────────────────────────────────────
def processar_lote(arquivos: list[tuple[str, str]], cache_dir: str | None,
                   paralelo: int, log=print):
    from .core import controller
    from .core.controller import ErroProcessamento, ResultadoLote

    res = ResultadoLote()
    res.total = len(arquivos)
    if cache_dir:
        os.makedirs(cache_dir, exist_ok=True)
    jobs = [(pdf, forn, cache_dir) for pdf, forn in arquivos]
    t0 = time.time()
    do_cache = 0
    passo = max(1, res.total // 40)

    def _consumir(item):
        nonlocal do_cache
        pdf, forn, resultados, erro, veio_do_cache = item
        nome = os.path.basename(pdf)
        do_cache += bool(veio_do_cache)
        if erro:
            res.erros.append(ErroProcessamento(arquivo=nome, fornecedor=forn, mensagem=erro))
        else:
            aproveitados = 0
            for resultado in resultados:
                if controller._fatura_ilegivel(resultado):
                    fid = (resultado.get("fatura") or {}).get("id_fatura", "?")
                    res.erros.append(ErroProcessamento(
                        arquivo=nome, fornecedor=forn,
                        mensagem=f"fatura {fid} DESCARTADA: nenhum item legível "
                                 "(digitalização ruim/ilegível)"))
                    continue
                res.dataset.adicionar_resultado(resultado)
                aproveitados += 1
            if aproveitados == 0 and resultados:
                res.erros.append(ErroProcessamento(
                    arquivo=nome, fornecedor=forn,
                    mensagem="fatura descartada: nenhum item legível"))
        res.processados += 1
        if res.processados % passo == 0 or res.processados == res.total:
            dt = time.time() - t0
            log(f"  {res.processados}/{res.total}  ({dt:,.0f}s; {do_cache} do cache; "
                f"{len(res.erros)} erro(s))")

    if paralelo <= 1 or res.total < 4:
        for j in jobs:
            _consumir(_processar_um(j))
    else:
        with cf.ProcessPoolExecutor(max_workers=paralelo) as ex:
            for item in ex.map(_processar_um, jobs, chunksize=4):
                _consumir(item)
    return res


def consolidar(res, modo_link: str, template: str | None, log=print):
    """Pós-processamento idêntico ao da aba Processar."""
    from .core import derivados, glossario, hardcodes, links
    from .core.profile import Perfil
    dfs = res.dataset.to_dataframes()
    dfs["fatura"] = links.aplicar_link(dfs["fatura"], modo_link, template)
    derivados.aplicar(dfs)
    rel_hc = hardcodes.aplicar_dfs(dfs)
    for linha in rel_hc:
        log(f"  hardcode: {linha}")
    perfil = Perfil.padrao_de_dataframes(dfs)
    display = glossario.garantir_glossario(perfil.aplicar(dfs))
    return dfs, display, perfil


def gravar_csv(display: dict, pasta: str, log=print) -> None:
    """Um CSV por aba (';' e vírgula decimal — o que o Excel pt-BR espera)."""
    os.makedirs(pasta, exist_ok=True)
    for aba, df in display.items():
        if aba.startswith("_"):
            continue
        fp = os.path.join(pasta, f"{aba}.csv")
        df.to_csv(fp, sep=";", decimal=",", index=False, encoding="utf-8-sig")
    log(f"CSV por aba em: {pasta}")


# ──────────────────────────────────────────────────────────────────────────────
# main
# ──────────────────────────────────────────────────────────────────────────────
def _args(argv):
    p = argparse.ArgumentParser(
        prog="faturas-cli",
        description="Processador de Faturas de Energia — modo linha de comando "
                    f"(v{__version__}).")
    p.add_argument("--pasta", action="append", metavar="DIR[=FORNECEDOR]",
                   help="pasta com PDFs de ENERGIA; repita para várias. FORNECEDOR = EQUATORIAL ou "
                        "CHESP (se omitido, vem do nome da pasta).")
    p.add_argument("--agua", action="append", metavar="DIR",
                   help="pasta com PDFs de ÁGUA (qualquer concessionária; subpastas sempre incluídas). "
                        "Repita para várias. Não combine com --pasta na mesma execução.")
    p.add_argument("--mapa-contas", metavar="ARQ", help="água: importar este mapa de contas (contas.json/xlsx/csv) antes")
    p.add_argument("--sem-ocr", action="store_true", help="água: não aplicar OCR nos PDFs digitalizados")
    p.add_argument("--subpastas", action="store_true", help="incluir subpastas")
    p.add_argument("--saida", required=True, metavar="ARQ.xlsx", help="planilha de saída")
    p.add_argument("--csv", metavar="DIR", help="também gravar um CSV por aba nesta pasta")
    p.add_argument("--cache", metavar="DIR",
                   help="cache JSON por PDF (padrão: <pasta da saída>\\cache_faturas; "
                        "'-' desliga)")
    p.add_argument("--paralelo", type=int, default=max(1, (os.cpu_count() or 2) - 1),
                   metavar="N", help="processos em paralelo (padrão: CPUs-1)")
    p.add_argument("--link", default="busca_drive",
                   choices=["busca_drive", "local", "template"],
                   help="modo da coluna link_pdf (padrão: busca_drive)")
    p.add_argument("--template", help="modelo de URL para --link template")
    p.add_argument("--mapa-uc", metavar="ARQ", help="importar este mapa de UCs (JSON/xlsx) antes")
    p.add_argument("--sem-medidor", action="store_true",
                   help="com mapa: desligar a identificação histórica por medidor")
    p.add_argument("--sem-extras", action="store_true",
                   help="ao importar o mapa, não criar colunas extras")
    p.add_argument("--log", metavar="ARQ", help="gravar o log também neste arquivo")
    return p.parse_args(argv)


def _main_agua(a, saida: str, log) -> int:
    """Modo ÁGUA: todas as concessionárias no mesmo modelo de planilha."""
    from .core.agua import controller_agua, mapa_conta

    if a.mapa_contas:
        m = mapa_conta.importar(a.mapa_contas)
        log(f"Mapa de contas importado: {m['total_contas']} conta(s).")
    if mapa_conta.ativo():
        m = mapa_conta.metadados()
        log(f"Mapa de contas ativo: {m['total_contas']} conta(s) ({m['origem']}).")
    else:
        log("Sem mapa de contas: conta_canonica = dígitos da conta; sem unidade institucional.")
    pastas = [os.path.abspath(p) for p in a.agua]
    total = controller_agua.contar_pdfs(pastas)
    if not total:
        raise SystemExit("Nenhum PDF encontrado.")
    cache = None if a.cache == "-" else (a.cache or os.path.join(os.path.dirname(saida), "cache_agua"))
    log(f"{total} PDF(s) de água em {len(pastas)} pasta(s)." + (f" Cache: {cache}" if cache else ""))
    passo = max(1, total // 40)

    def prog(i, n, nome):
        if i % passo == 0 or i == n:
            log(f"  {i}/{n} — {nome}")

    lote = controller_agua.processar_pastas(pastas, prog, cache_dir=cache, ocr=not a.sem_ocr, paralelo=a.paralelo,
                                            modo_link=a.link, template=a.template)
    log(lote.resumo())
    dfs = controller_agua.dataframes(lote)
    controller_agua.escrever_planilha(dfs, saida)
    log(f"Planilha: {saida}")
    if a.csv:
        controller_agua.gravar_csv(dfs, os.path.abspath(a.csv))
        log(f"CSV por aba em: {os.path.abspath(a.csv)}")
    if lote.erros:
        fp_err = os.path.splitext(saida)[0] + "_erros.txt"
        with open(fp_err, "w", encoding="utf-8") as f:
            for e in lote.erros:
                f.write(f"{e.arquivo}: {e.mensagem}\n")
        log(f"Erros: {fp_err}")
    for av in lote.resultado.avisos[:20]:
        log(f"  aviso: {av}")
    cont: dict[str, int] = {}
    for v in lote.validacao:
        cont[v["gravidade"]] = cont.get(v["gravidade"], 0) + 1
    if cont:
        log("Validação: " + ", ".join(f"{k} {v}" for k, v in cont.items()) + " (aba 'validacao_agua').")
    log("Linhas por aba: " + ", ".join(f"{k} {len(df)}" for k, df in dfs.items()))
    return 0


def main(argv=None) -> int:
    a = _args(argv if argv is not None else sys.argv[1:])
    saida = os.path.abspath(a.saida)
    if not saida.lower().endswith(".xlsx"):
        saida += ".xlsx"
    os.makedirs(os.path.dirname(saida), exist_ok=True)
    log_fp = open(a.log, "a", encoding="utf-8") if a.log else None

    def log(msg=""):
        print(msg, flush=True)
        if log_fp:
            log_fp.write(msg + "\n")
            log_fp.flush()

    log(f"== Processador de Faturas de Energia v{__version__} — modo CLI ==")
    if a.agua and a.pasta:
        raise SystemExit("Use --pasta (energia) OU --agua (água), não os dois na mesma execução.")
    if not a.agua and not a.pasta:
        raise SystemExit("Informe --pasta (energia) ou --agua (água).")
    if a.agua:
        rc = _main_agua(a, saida, log)
        if log_fp:
            log_fp.close()
        return rc
    if a.mapa_uc:
        importar_mapa_uc(a.mapa_uc, usar_medidor=not a.sem_medidor,
                         extras=not a.sem_extras, log=log)
    from .core import dicionario_uc
    if dicionario_uc.ativo():
        m = dicionario_uc.metadados()
        log(f"Mapa de UCs ativo: {m['total_ucs']} UC(s) ({m['arquivo']}).")
    else:
        log("Sem mapa de UCs: a planilha sai sem id_uc_canonico nem cadastro.")

    arquivos = []
    for spec in a.pasta:
        arquivos += _listar(spec, a.subpastas)
    if not arquivos:
        raise SystemExit("Nenhum PDF encontrado.")
    por_forn = {f: sum(1 for _, x in arquivos if x == f) for f in FORNECEDORES}
    log(f"{len(arquivos)} PDF(s): " + ", ".join(f"{k} {v}" for k, v in por_forn.items() if v))

    cache = None if a.cache == "-" else (a.cache or os.path.join(os.path.dirname(saida), "cache_faturas"))
    if cache:
        log(f"Cache: {cache}")
    t0 = time.time()
    res = processar_lote(arquivos, cache, a.paralelo, log=log)
    log(f"Processamento: {res.dataset.total_faturas()} fatura(s) em {time.time() - t0:,.0f}s; "
        f"{len(res.erros)} erro(s).")

    log("Consolidando (colunas derivadas, tarifas, validação, hardcodes)…")
    dfs, display, perfil = consolidar(res, a.link, a.template, log=log)
    from .core import excel_io
    excel_io.escrever_workbook(display, perfil.to_meta(), saida)
    log(f"Planilha: {saida}")
    if a.csv:
        gravar_csv(display, os.path.abspath(a.csv), log=log)

    if res.erros:
        fp_err = os.path.splitext(saida)[0] + "_erros.txt"
        with open(fp_err, "w", encoding="utf-8") as f:
            for e in res.erros:
                f.write(f"[{e.fornecedor}] {e.arquivo}: {e.mensagem}\n")
        log(f"Erros: {fp_err}")
    val = dfs.get("validacao")
    if val is not None and not val.empty:
        cont = val["gravidade"].value_counts().to_dict()
        log("Validação: " + ", ".join(f"{k} {v}" for k, v in cont.items())
            + " (aba 'validacao').")
    linhas = {aba: len(df) for aba, df in dfs.items()}
    log("Linhas por aba: " + ", ".join(f"{k} {v}" for k, v in linhas.items()))
    if log_fp:
        log_fp.close()
    return 0
