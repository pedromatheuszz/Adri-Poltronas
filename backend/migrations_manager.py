"""Gerenciador de migrações do banco de dados."""
import logging
import os
import sqlite3
import sys

from alembic.config import Config
from alembic import command
from alembic.script import ScriptDirectory

import database

log = logging.getLogger("adri.migrations")


def _raiz_recursos() -> str:
    """Diretório onde vivem alembic.ini e migrations/ (bundle ou repositório)."""
    if getattr(sys, 'frozen', False):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))


def _config() -> Config:
    """
    Monta a Config do Alembic com caminhos absolutos.

    Usar `Config("alembic.ini")` resolveria relativo ao CWD e só funcionaria
    quando o processo fosse iniciado de dentro de backend/ — fora disso o
    upgrade falhava silenciosamente e o app caía no fallback criar_tabela().
    """
    raiz = _raiz_recursos()
    caminho_ini = os.path.join(raiz, 'alembic.ini')
    if not os.path.exists(caminho_ini):
        raise FileNotFoundError(f"alembic.ini nao encontrado em {caminho_ini}")

    cfg = Config(caminho_ini)
    cfg.set_main_option('script_location', os.path.join(raiz, 'migrations'))
    # O sqlalchemy.url precisa apontar para o mesmo banco que a aplicacao usa.
    caminho_bd = database.obter_caminho_banco_absoluto().replace('\\', '/')
    cfg.set_main_option('sqlalchemy.url', f'sqlite:///{caminho_bd}')
    return cfg


def revisao_do_banco() -> str | None:
    """
    Revisão gravada em `alembic_version`, lida direto do arquivo.

    `None` significa banco novo (a tabela ainda não existe) — e banco novo não
    tem nada a perder, então não justifica backup.
    """
    caminho = database.obter_caminho_banco_absoluto()
    if not os.path.exists(caminho):
        return None
    try:
        conexao = sqlite3.connect(f"file:{caminho}?mode=ro", uri=True, timeout=5)
    except sqlite3.Error:
        return None
    try:
        linha = conexao.execute("SELECT version_num FROM alembic_version").fetchone()
        return linha[0] if linha else None
    except sqlite3.Error:
        return None
    finally:
        conexao.close()


def revisao_alvo() -> str | None:
    """Cabeça da cadeia de migrations no código."""
    try:
        return ScriptDirectory.from_config(_config()).get_current_head()
    except Exception:
        log.warning("Não foi possível determinar a cabeça das migrations.")
        return None


def ha_migracoes_pendentes() -> bool:
    """
    Verdadeiro só quando o banco existente está atrás do código.

    É o gatilho do backup de pré-migração: sem esta checagem, toda abertura do
    app geraria uma cópia, e a rotação descartaria justamente as que
    antecedem uma mudança de schema.
    """
    atual = revisao_do_banco()
    if atual is None:
        return False
    alvo = revisao_alvo()
    return alvo is not None and atual != alvo


def aplicar_migrações():
    """Aplica todas as migrações pendentes."""
    try:
        command.upgrade(_config(), "head")
        log.info("Migrações aplicadas com sucesso.")
    except Exception as e:
        log.error("Erro ao aplicar migrações: %s", e)
        raise


def verificar_migrações():
    """Verifica se há migrações pendentes."""
    try:
        return command.current(_config())
    except Exception as e:
        log.error("Erro ao verificar migrações: %s", e)
        return None
