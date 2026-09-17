"""Mapa de CONTAS de água: cadastro (conta → fornecedor, unidade institucional, hidrômetro, água/esgoto/SMRSU).

É o equivalente, para a água, do mapa de UCs da energia. Fica em `%APPDATA%/FaturasEnergia/mapa_contas_agua.json` e pode ser:
  * importado do `contas.json` do projeto original (campos CONTA_DV, CONTA, UNIDADE, ENDERECO, DISTRIBUIDORA, OPERANTE,
    AGUA, ESGOTO, SMRSU) ou de uma planilha com colunas parecidas;
  * construído automaticamente a partir das próprias faturas extraídas (`construir_de_extracao`): conta, fornecedor, nome
    do cliente, logradouro, hidrômetro e as categorias que apareceram com valor.

A conta canônica é a conta em dígitos (sem pontuação e sem zeros à esquerda) dentro do fornecedor; um registro pode ter
vários identificadores (a mesma conta impressa de formas diferentes)."""
from __future__ import annotations

import json
import os
import re
import unicodedata
from pathlib import Path

from .texto import digitos, sem_acento

_NOME = "mapa_contas_agua.json"
_CACHE: dict | None = None


def _dir_usuario() -> Path:
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    d = Path(base) / "FaturasEnergia"
    d.mkdir(parents=True, exist_ok=True)
    return d


def arquivo() -> Path:
    return _dir_usuario() / _NOME


def chave(conta, fornecedor: str | None = None) -> str | None:
    """Conta canônica: só dígitos, sem zeros à esquerda (`1627885 2` → `16278852`; `0001255.2` → `12552`)."""
    d = digitos(conta).lstrip("0")
    if not d:
        return None
    return f"{fornecedor}:{d}" if fornecedor else d


def _bool(v) -> bool | None:
    if v is None or v == "":
        return None
    if isinstance(v, bool):
        return v
    s = sem_acento(str(v)).strip().lower()
    return s in ("1", "true", "sim", "s", "x", "yes")


def _carregar() -> dict:
    global _CACHE
    if _CACHE is None:
        try:
            _CACHE = json.loads(arquivo().read_text(encoding="utf-8"))
        except Exception:
            _CACHE = {"registros": [], "origem": None}
        _indexar(_CACHE)
    return _CACHE


def _indexar(dados: dict):
    idx = {}
    for r in dados.get("registros", []):
        for ident in r.get("identificadores") or [r.get("conta_canonica")]:
            k = chave(ident, r.get("fornecedor"))
            if k:
                idx[k] = r
            k2 = chave(ident)
            if k2 and k2 not in idx:
                idx[k2] = r
    dados["_indice"] = idx


def recarregar():
    global _CACHE
    _CACHE = None


def ativo() -> bool:
    return bool(_carregar().get("registros"))


def registros() -> list[dict]:
    return list(_carregar().get("registros", []))


def metadados() -> dict:
    d = _carregar()
    return {"total_contas": len(d.get("registros", [])), "origem": d.get("origem"), "arquivo": str(arquivo())}


def buscar(conta, fornecedor: str | None = None) -> dict | None:
    idx = _carregar().get("_indice", {})
    if fornecedor:
        r = idx.get(chave(conta, fornecedor))
        if r:
            return r
    return idx.get(chave(conta))


def canonica(conta, fornecedor: str | None = None) -> str | None:
    """Conta canônica pelo mapa; sem mapa (ou conta desconhecida) cai para os dígitos da própria conta."""
    r = buscar(conta, fornecedor)
    if r:
        return r["conta_canonica"]
    return chave(conta)


def salvar(regs: list[dict], origem: str | None = None) -> dict:
    global _CACHE
    limpos = []
    for r in regs:
        c = chave(r.get("conta_canonica") or (r.get("identificadores") or [""])[0])
        if not c:
            continue
        ids = [digitos(x) for x in (r.get("identificadores") or []) if digitos(x)]
        if c not in [i.lstrip("0") for i in ids]:
            ids.insert(0, c)
        limpos.append({**r, "conta_canonica": c, "identificadores": ids})
    dados = {"registros": limpos, "origem": origem}
    arquivo().write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")
    _CACHE = None
    return metadados()


def limpar():
    global _CACHE
    try:
        arquivo().unlink()
    except FileNotFoundError:
        pass
    _CACHE = None


# ── importação do contas.json / planilha ───────────────────────────────────────
_CAMPOS = {
    "conta_dv": "conta_formatada", "conta": "conta_canonica", "unidade": "unidade_institucional",
    "unidade judiciaria": "unidade_institucional", "unidade_judiciaria": "unidade_institucional",
    "endereco": "logradouro", "distribuidora": "fornecedor", "fornecedor": "fornecedor", "operante": "operante",
    "agua": "agua", "esgoto": "esgoto", "smrsu": "smrsu", "hidrometro": "hidrometro", "cidade": "cidade",
    "nome": "nome_cliente", "nome_cliente": "nome_cliente",
}
_FORN_APELIDOS = {
    "saneago": "SANEAGO", "sae": "SAE_CATALAO", "sae catalao": "SAE_CATALAO", "demae": "DEMAE_CALDAS_NOVAS",
    "demae caldas novas": "DEMAE_CALDAS_NOVAS", "demae panama": "DEMAE_PANAMA", "demaep": "DEMAE_PANAMA",
    "saae abadiania": "SAAE_ABADIANIA", "abadiania": "SAAE_ABADIANIA", "saae corumba": "SAAE_CORUMBA", "corumba": "SAAE_CORUMBA",
    "saae mineiros": "SAAE_MINEIROS", "mineiros": "SAAE_MINEIROS", "sanesc": "SANESC", "sao simao": "SAO_SIMAO_SA",
    "sssa": "SAO_SIMAO_SA", "leopoldo de bulhoes": "SAAE_LEOPOLDO_BULHOES", "saae leopoldo de bulhoes": "SAAE_LEOPOLDO_BULHOES",
    "ipameri": "AGUAS_IPAMERI", "aguas de ipameri": "AGUAS_IPAMERI", "buriti alegre": "BURITI_ALEGRE_AMBIENTAL",
    "buriti alegre ambiental": "BURITI_ALEGRE_AMBIENTAL", "codego": "CODEGO",
}


def _n(s) -> str:
    return re.sub(r"\s+", " ", sem_acento(str(s or "")).strip().lower())


def normalizar_fornecedor(v) -> str | None:
    if not v:
        return None
    s = _n(v)
    if s.upper() in _FORN_APELIDOS.values():
        return s.upper()
    for k, f in sorted(_FORN_APELIDOS.items(), key=lambda kv: -len(kv[0])):
        if k in s:
            return f
    return None


def _ler_bruto(caminho: str) -> list[dict]:
    if caminho.lower().endswith(".json"):
        dados = json.loads(Path(caminho).read_text(encoding="utf-8"))
        if isinstance(dados, dict):
            dados = dados.get("registros") or dados.get("contas") or list(dados.values())
        return [dict(r) for r in dados if isinstance(r, dict)]
    import pandas as pd
    df = pd.read_excel(caminho) if caminho.lower().endswith((".xlsx", ".xls")) else pd.read_csv(caminho, sep=None, engine="python")
    return [{str(k): (None if (isinstance(v, float) and v != v) else v) for k, v in r.items()} for r in df.to_dict("records")]


def importar(caminho: str) -> dict:
    """Importa contas.json (projeto original) ou planilha com colunas parecidas e salva como mapa."""
    regs = []
    for bruto in _ler_bruto(caminho):
        r: dict = {}
        for k, v in bruto.items():
            alvo = _CAMPOS.get(_n(k).replace(" ", "_")) or _CAMPOS.get(_n(k))
            if alvo:
                r[alvo] = v
        conta_fmt = r.get("conta_formatada")
        conta = r.get("conta_canonica") or conta_fmt
        if not digitos(conta):
            continue
        ids = [x for x in (conta_fmt, conta) if digitos(x)]
        regs.append({
            "conta_canonica": chave(conta), "identificadores": ids, "conta_formatada": str(conta_fmt or conta),
            "fornecedor": normalizar_fornecedor(r.get("fornecedor")),
            "unidade_institucional": r.get("unidade_institucional"), "logradouro": r.get("logradouro"),
            "cidade": r.get("cidade"), "nome_cliente": r.get("nome_cliente"), "hidrometro": r.get("hidrometro"),
            "agua": _bool(r.get("agua")), "esgoto": _bool(r.get("esgoto")), "smrsu": _bool(r.get("smrsu")),
            "operante": _bool(r.get("operante")), "origem": os.path.basename(caminho),
        })
    return salvar(regs, origem=os.path.basename(caminho))


# ── construção automática a partir das faturas extraídas ──────────────────────
_RE_UNIDADE = re.compile(r"(F[OÓ]RUM[A-Z ./]*|JUIZADO[A-Z ./]*|TRIBUNAL[A-Z ./]*|COMARCA[A-Z ./]*)", re.IGNORECASE)


def unidade_do_nome(nome_cliente: str | None, logradouro: str | None = None) -> str | None:
    """'FORUM DE ITAPACI' → 'FORUM DE ITAPACI'; 'TRIBUNAL DE JUSTIÇA DO ESTADO DE GO' + logradouro com a cidade no fim
    → 'TRIBUNAL DE JUSTIÇA (ACREUNA)'. Melhor esforço; o contas.json real substitui."""
    n = (nome_cliente or "").strip()
    if not n:
        return None
    if re.search(r"F[OÓ]RUM|JUIZADO|VARA|CRECHE|ANEXO|PALACIO|COORDENADORIA", n, re.IGNORECASE):
        return n
    cidade = None
    if logradouro:
        partes = re.split(r"\s{2,}|,", logradouro.strip())
        cidade = partes[-1].strip() if partes else None
        if cidade and len(cidade.split()) > 4:
            cidade = " ".join(cidade.split()[-3:])
    return f"{n} ({cidade})" if cidade else n


def construir_de_extracao(faturas: list[dict], contas_bordero: list[dict], origem: str = "extração") -> list[dict]:
    """Um registro por (fornecedor, conta canônica), consolidando o que as faturas e os borderôs imprimem."""
    acc: dict[str, dict] = {}
    for src, linhas in (("fatura", faturas), ("bordero", contas_bordero)):
        for f in linhas:
            forn = f.get("fornecedor")
            c = chave(f.get("conta"), forn)
            if not c:
                continue
            r = acc.setdefault(c, {"conta_canonica": chave(f.get("conta")), "identificadores": [], "fornecedor": forn,
                                   "conta_formatada": None, "nome_cliente": None, "logradouro": None, "hidrometro": None,
                                   "cidade": None, "agua": False, "esgoto": False, "smrsu": False, "operante": True,
                                   "primeira_competencia": None, "ultima_competencia": None, "faturas": 0, "origem": origem})
            cf = str(f.get("conta_formatada") or f.get("conta") or "")
            if cf and digitos(cf) not in [digitos(x) for x in r["identificadores"]]:
                r["identificadores"].append(cf)
            if not r["conta_formatada"] and cf:
                r["conta_formatada"] = cf
            for k in ("nome_cliente", "logradouro", "hidrometro"):
                if f.get(k) and (not r[k] or len(str(f[k])) > len(str(r[k]))):
                    r[k] = f[k]
            for k, col in (("agua", "valor_agua"), ("esgoto", "valor_esgoto"), ("smrsu", "valor_smrsu" if src == "bordero" else "valor_taxas")):
                try:
                    if float(f.get(col) or 0) > 0:
                        r[k] = True
                except (TypeError, ValueError):
                    pass
            comp = f.get("competencia")
            if comp:
                r["primeira_competencia"] = min(r["primeira_competencia"] or comp, comp)
                r["ultima_competencia"] = max(r["ultima_competencia"] or comp, comp)
            if src == "fatura":
                r["faturas"] += 1
    for r in acc.values():
        r["unidade_institucional"] = unidade_do_nome(r.get("nome_cliente"), r.get("logradouro"))
        if r.get("logradouro"):
            partes = re.split(r"\s{2,}", r["logradouro"].strip())
            r["cidade"] = partes[-1][-40:] if partes else None
    return sorted(acc.values(), key=lambda r: (r["fornecedor"] or "", r["conta_canonica"]))
