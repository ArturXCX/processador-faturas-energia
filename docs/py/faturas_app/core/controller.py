"""
Orquestração do processamento: percorre as pastas/fornecedores selecionados,
processa cada PDF e reporta progresso. Sem dependência de interface (a GUI passa
callbacks). Pode ser cancelado por um threading.Event.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from glob import glob

from . import equatorial, chesp
from .dataset import Dataset, _RE_ITEM_INFORMATIVO

# O processador pode devolver UM resultado (dict) ou uma LISTA de resultados
# (PDF com várias faturas mescladas — ver equatorial.processar_pdf_multi).
PROCESSADORES = {
    "EQUATORIAL": equatorial.processar_pdf_multi,
    "CHESP":      chesp.processar_pdf,
}


@dataclass
class Job:
    pasta: str
    fornecedor: str          # "EQUATORIAL" ou "CHESP"
    incluir_subpastas: bool = False


@dataclass
class ErroProcessamento:
    arquivo: str
    fornecedor: str
    mensagem: str


@dataclass
class ResultadoLote:
    dataset: Dataset = field(default_factory=Dataset)
    erros: list[ErroProcessamento] = field(default_factory=list)
    total: int = 0
    processados: int = 0
    cancelado: bool = False


def listar_pdfs(pasta: str, incluir_subpastas: bool = False) -> list[str]:
    if incluir_subpastas:
        achados = []
        for raiz, _dirs, arqs in os.walk(pasta):
            for a in arqs:
                if a.lower().endswith(".pdf"):
                    achados.append(os.path.join(raiz, a))
        return sorted(achados)
    return sorted(glob(os.path.join(pasta, "*.pdf")))


def contar_pdfs(jobs: list[Job]) -> int:
    return sum(len(listar_pdfs(j.pasta, j.incluir_subpastas)) for j in jobs)


def _fatura_ilegivel(resultado: dict) -> bool:
    """
    Fatura com valor total mas NENHUM item aproveitável (ex.: digitalização
    ruim, OCR não recupera a tabela de itens — caso ORIZONA.pdf). Essas
    faturas são DESCARTADAS por completo, com registro no log de erros, para
    não entrar na planilha uma fatura cuja soma de itens nunca fecharia.
    """
    fat = resultado.get("fatura") or {}
    total = fat.get("valor_total_r$")
    itens = [r for r in (resultado.get("itens_fatura") or [])
             if not _RE_ITEM_INFORMATIVO.search(str(r.get("item", "")))]
    return total is not None and total > 0 and not itens


def processar_jobs(jobs: list[Job], progresso=None, cancelar=None) -> ResultadoLote:
    """
    Processa todos os PDFs dos jobs.

    progresso(feito:int, total:int, nome_arquivo:str, fornecedor:str, ok:bool, msg:str)
        callback opcional chamado após CADA arquivo.
    cancelar() -> bool
        callback opcional; se retornar True, interrompe o lote.
    """
    res = ResultadoLote()
    arquivos: list[tuple[str, str]] = []
    for j in jobs:
        for p in listar_pdfs(j.pasta, j.incluir_subpastas):
            arquivos.append((p, j.fornecedor))
    res.total = len(arquivos)

    for path, forn in arquivos:
        if cancelar and cancelar():
            res.cancelado = True
            break
        nome = os.path.basename(path)
        ok, msg = True, ""
        try:
            fn = PROCESSADORES[forn.upper()]
            r = fn(path)
            resultados = r if isinstance(r, list) else [r]
            aproveitados = 0
            for resultado in resultados:
                if _fatura_ilegivel(resultado):
                    fid = (resultado.get("fatura") or {}).get("id_fatura", "?")
                    m = (f"fatura {fid} DESCARTADA: nenhum item legível "
                         "(digitalização ruim/ilegível)")
                    res.erros.append(ErroProcessamento(
                        arquivo=nome, fornecedor=forn, mensagem=m))
                    continue
                res.dataset.adicionar_resultado(resultado)
                aproveitados += 1
            if aproveitados == 0 and resultados:
                ok = False
                msg = "fatura descartada: nenhum item legível (digitalização ruim/ilegível)"
        except Exception as e:  # noqa: BLE001 — registramos e seguimos
            ok = False
            msg = str(e)
            res.erros.append(ErroProcessamento(arquivo=nome, fornecedor=forn, mensagem=msg))
        res.processados += 1
        if progresso:
            progresso(res.processados, res.total, nome, forn, ok, msg)
    return res
