"""
Conexao SQLite do v2.

Banco SEPARADO do v1 de proposito. Enquanto os dois backends coexistem, o v2
nao pode tocar em `adri_poltronas.db`: os esquemas sao incompativeis (dinheiro
inteiro, titulos com baixa, estoque como razao) e uma migracao acidental
tornaria a volta ao v1 impossivel.
"""
from __future__ import annotations

import os
import pathlib
import sqlite3

NOME_BANCO = "adri_poltronas_v2.db"

_ESQUEMA = pathlib.Path(__file__).with_name("esquema.sql")


def caminho_banco() -> str:
    override = os.environ.get("ADRI_V2_DB_PATH")
    if override:
        return override
    appdata = os.environ.get("APPDATA")
    if appdata:
        pasta = pathlib.Path(appdata) / "AdriPoltronas"
        try:
            pasta.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        else:
            return str(pasta / NOME_BANCO)
    return str(pathlib.Path(__file__).resolve().parents[2] / NOME_BANCO)


def conectar(caminho: str | None = None) -> sqlite3.Connection:
    conexao = sqlite3.connect(caminho or caminho_banco(), timeout=15, isolation_level=None)
    conexao.row_factory = sqlite3.Row
    # FK precisa ser ligada por conexao: sem isto as constraints do esquema sao
    # decorativas, e foi assim que o v1 deixou gravar pagamento apontando para
    # cliente inexistente.
    conexao.execute("PRAGMA foreign_keys = ON")
    conexao.execute("PRAGMA busy_timeout = 15000")
    # WAL: leitura nao bloqueia escrita. Num ERP com relatorio longo rodando
    # enquanto alguem lanca pedido, o modo default trava um dos dois.
    conexao.execute("PRAGMA journal_mode = WAL")
    conexao.execute("PRAGMA synchronous = NORMAL")
    return conexao


def criar_esquema(conexao: sqlite3.Connection) -> None:
    """Aplica o DDL. Idempotente -- tudo e IF NOT EXISTS."""
    conexao.executescript(_ESQUEMA.read_text(encoding="utf-8"))


def preparar_banco(caminho: str | None = None) -> str:
    alvo = caminho or caminho_banco()
    conexao = conectar(alvo)
    try:
        criar_esquema(conexao)
    finally:
        conexao.close()
    return alvo
