"""
Geração da coluna `link_pdf` (link do PDF da fatura) sem exigir login/credenciais.

Modos:
  - LOCAL    : não gera link (mantém apenas `caminho_pdf`, o caminho local).
  - BUSCA    : link de busca no Google Drive pelo NOME do arquivo
               (drive.google.com/drive/search?q=...). Zero configuração; clicar
               abre o Drive já buscando aquela fatura.
  - TEMPLATE : modelo de URL definido pelo usuário, com marcadores substituídos:
               {arquivo}          -> nome do PDF (ex.: 10001867464.pdf)
               {arquivo_sem_ext}  -> nome sem extensão (ex.: 10001867464)

Obs.: o link EXATO de cada arquivo (drive.google.com/file/d/<id>/view) exige a
API do Google Drive (login/credenciais) e não é coberto aqui — ver README.
"""
from __future__ import annotations

import os
from urllib.parse import quote

import pandas as pd

MODO_LOCAL = "local"
MODO_BUSCA = "busca_drive"
MODO_TEMPLATE = "template"

# Modelo padrão sugerido na interface para o modo TEMPLATE.
TEMPLATE_EXEMPLO = "https://drive.google.com/drive/search?q={arquivo_sem_ext}"


def gerar_link(modo: str, arquivo_pdf, caminho_pdf=None, template: str | None = None):
    nome = str(arquivo_pdf or "").strip()
    if not nome:
        return None
    sem_ext = os.path.splitext(nome)[0]

    if modo == MODO_BUSCA:
        return f"https://drive.google.com/drive/search?q={quote(sem_ext)}"

    if modo == MODO_TEMPLATE and template:
        return (template
                .replace("{arquivo_sem_ext}", sem_ext)
                .replace("{arquivo}", nome))

    return None  # MODO_LOCAL ou modelo vazio


def aplicar_link(df_fatura: pd.DataFrame, modo: str, template: str | None = None) -> pd.DataFrame:
    """Preenche a coluna `link_pdf` na aba fatura conforme o modo escolhido."""
    if df_fatura is None or df_fatura.empty or "arquivo_pdf" not in df_fatura.columns:
        return df_fatura
    df = df_fatura.copy()
    caminhos = df["caminho_pdf"] if "caminho_pdf" in df.columns else [None] * len(df)
    df["link_pdf"] = [
        gerar_link(modo, arq, cam, template)
        for arq, cam in zip(df["arquivo_pdf"], caminhos)
    ]
    return df
