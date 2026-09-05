from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
#
# `disable_existing_loggers=False` nao e detalhe: o padrao do `fileConfig` e
# True, e True aqui significa DESLIGAR todo logger ja criado que nao esteja
# declarado em alembic.ini. Como `servidor.py` importa `app` (que cria
# `adri.app`, `adri.asaas`, `adri.security`, `adri.db`, `adri.capacidade`)
# ANTES de chamar `preparar_banco()`, e a preparacao roda `command.upgrade`
# em todo boot, o efeito era este: a partir da primeira migracao de cada
# execucao, o aplicativo parava de escrever no proprio `app.log`.
#
# Some com os avisos que sustentam a auditoria -- "[AUTH] Requisicao sem
# sessao bloqueada", "[CAPACIDADE] Requisicao sem token", "[SEGURANCA] Host
# recusado" -- e com o log que o QUICK_REFERENCE manda o operador enviar
# quando algo da errado. Falha silenciosa: nada quebra, o arquivo existe, e
# so nao tem dentro o que deveria ter.
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata
target_metadata = None

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
