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


# Estados possiveis do arquivo de banco. Existem porque a pergunta "ha
# migracao pendente?" nao tem resposta util sem antes saber COM O QUE se esta
# lidando -- e a versao anterior deste modulo tratava tres situacoes muito
# diferentes como a mesma coisa (`None`):
#
#   arquivo inexistente | banco legado sem alembic_version | banco ilegivel
#
# Consequencia pratica do empate: um banco legado, cheio de clientes reais,
# respondia "nao ha migracao pendente" e seguia direto para o upgrade SEM
# BACKUP. Era exatamente o caso em que a copia mais importava.
ESTADO_AUSENTE = "ausente"        # o arquivo nao existe: instalacao nova
ESTADO_VAZIO = "vazio"            # existe, mas sem nenhuma tabela de dados
ESTADO_LEGADO = "legado"          # tem dados e nao tem alembic_version
ESTADO_VERSIONADO = "versionado"  # tem alembic_version legivel
ESTADO_ILEGIVEL = "ilegivel"      # existe e nao abre, ou nao responde consulta

# Estados em que nao ha nada a perder. Tudo que estiver FORA deste conjunto
# exige backup antes de migrar e proibe o fallback de schema.
ESTADOS_SEM_DADOS = frozenset({ESTADO_AUSENTE, ESTADO_VAZIO})


def estado_do_banco() -> str:
    """
    Classifica o arquivo de banco antes de qualquer decisao sobre migracao.

    Nao levanta: um erro aqui vira `ESTADO_ILEGIVEL`, que e o estado mais
    conservador -- quem consome trata ilegivel como "tem dados", forcando
    backup e proibindo o fallback.
    """
    caminho = database.obter_caminho_banco_absoluto()
    if not os.path.exists(caminho) or os.path.getsize(caminho) == 0:
        return ESTADO_AUSENTE

    try:
        conexao = sqlite3.connect(f"file:{caminho}?mode=ro", uri=True, timeout=5)
    except sqlite3.Error:
        return ESTADO_ILEGIVEL

    try:
        tabelas = {
            linha[0]
            for linha in conexao.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
    except sqlite3.Error:
        return ESTADO_ILEGIVEL
    finally:
        conexao.close()

    # sqlite_sequence e criada sozinha por qualquer AUTOINCREMENT e nao conta
    # como dado do usuario.
    tabelas_de_dados = {t for t in tabelas if not t.startswith("sqlite_")}
    if not tabelas_de_dados:
        return ESTADO_VAZIO
    if "alembic_version" not in tabelas_de_dados:
        return ESTADO_LEGADO
    return ESTADO_VERSIONADO


def banco_tem_dados() -> bool:
    """Verdadeiro sempre que perder o arquivo custaria alguma coisa."""
    return estado_do_banco() not in ESTADOS_SEM_DADOS


def revisao_do_banco() -> str | None:
    """
    Revisão gravada em `alembic_version`, lida direto do arquivo.

    `None` cobre tres casos que o chamador NAO deve confundir entre si —
    arquivo ausente, banco legado e banco ilegivel. Quem precisa distinguir
    chama `estado_do_banco()`.
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
    Verdadeiro quando o Alembic vai mexer num banco que tem o que perder.

    É o gatilho do backup de pré-migração. Sem a checagem, toda abertura do
    app geraria uma cópia e a rotação descartaria justamente as que antecedem
    uma mudança de schema — por isso um banco já na cabeça responde `False`.

    Banco legado (sem `alembic_version`) e banco ilegível respondem `True`:
    são os dois casos em que o upgrade mais pode doer e em que a versão
    anterior desta função respondia, erradamente, `False`.
    """
    estado = estado_do_banco()
    if estado in ESTADOS_SEM_DADOS:
        return False
    if estado in (ESTADO_LEGADO, ESTADO_ILEGIVEL):
        return True
    alvo = revisao_alvo()
    return alvo is not None and revisao_do_banco() != alvo


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
