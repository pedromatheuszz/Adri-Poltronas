# backend/migrations_manager.py
"""Gerenciador de migrações do banco de dados."""
import logging
from alembic.config import Config
from alembic import command

log = logging.getLogger("adri.migrations")


def aplicar_migrações():
    """Aplica todas as migrações pendentes."""
    try:
        alembic_cfg = Config("alembic.ini")
        command.upgrade(alembic_cfg, "head")
        log.info("Migrações aplicadas com sucesso.")
    except Exception as e:
        log.error("Erro ao aplicar migrações: %s", e)
        raise


def verificar_migrações():
    """Verifica se há migrações pendentes."""
    try:
        alembic_cfg = Config("alembic.ini")
        return command.current(alembic_cfg)
    except Exception as e:
        log.error("Erro ao verificar migrações: %s", e)
        return None
