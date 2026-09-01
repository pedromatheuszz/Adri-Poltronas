"""
Backup automatico do banco local.

Por que existe: o banco fica num arquivo unico em `%APPDATA%`, sem replica e
sem servidor por tras. Uma migration malsucedida, um desligamento no meio de
uma escrita ou um erro de operacao levam junto a base inteira de clientes,
pagamentos e historico. Ate aqui o unico backup era manual -- e a funcao que
deveria faze-lo apontava para uma rota inexistente, entao na pratica nao havia
backup nenhum.

Dois momentos sao cobertos, e a escolha nao e arbitraria:

* **Antes de migrar** -- e a unica operacao que reescreve estrutura. Se algo
  der errado ali, o arquivo anterior e o que salva. So dispara quando ha
  migration pendente de verdade, entao abrir o app dez vezes no mesmo dia nao
  gera dez copias.
* **Uma vez por dia** -- cobre corrupcao, exclusao acidental e o erro de
  operacao que ninguem percebe na hora.

A copia usa a API `Connection.backup()` do SQLite, e nao `shutil.copy`. Copiar
o arquivo com o app aberto pode capturar um estado no meio de uma transacao, e
ainda deixa de fora o que estiver no `-wal`. A API online resolve os dois: le
uma pagina por vez com bloqueio proprio e entrega um banco integro.
"""
from __future__ import annotations

import logging
import os
import sqlite3
import time
from typing import Optional

log = logging.getLogger("adri.backup")

# Motivos possiveis. Sao usados no nome do arquivo e para rotacionar cada
# especie separadamente -- misturar as duas faria o backup diario expulsar o
# de pre-migracao justamente quando ele e mais necessario.
MOTIVO_PRE_MIGRACAO = "pre-migracao"
MOTIVO_DIARIO = "diario"

# Quantas copias manter de cada motivo. O banco tem poucas centenas de KB, mas
# sem teto a pasta cresce sem fim na maquina do usuario.
LIMITE_POR_MOTIVO = {
    MOTIVO_PRE_MIGRACAO: 10,
    MOTIVO_DIARIO: 7,
}
LIMITE_PADRAO = 5

PREFIXO = "adri_poltronas"


def pasta_de_backups(caminho_banco: str) -> str:
    """
    `backups/` ao lado do arquivo do banco.

    Segue o banco em vez de fixar %APPDATA%: assim a suite de testes, que
    aponta ADRI_DB_PATH para um diretorio temporario, nao escreve na pasta
    real do usuario.
    """
    return os.path.join(os.path.dirname(os.path.abspath(caminho_banco)), "backups")


def _nome_do_arquivo(motivo: str, momento: Optional[time.struct_time] = None) -> str:
    carimbo = time.strftime("%Y%m%d_%H%M%S", momento or time.localtime())
    return f"{PREFIXO}_{motivo}_{carimbo}.db"


def _copias_existentes(pasta: str, motivo: str) -> list:
    """Copias de um motivo, da mais recente para a mais antiga."""
    if not os.path.isdir(pasta):
        return []
    prefixo = f"{PREFIXO}_{motivo}_"
    arquivos = [
        os.path.join(pasta, nome)
        for nome in os.listdir(pasta)
        if nome.startswith(prefixo) and nome.endswith(".db")
    ]
    # Ordena pelo nome, e nao por mtime: o carimbo de tempo esta no proprio
    # nome, e copiar a pasta para outro lugar preserva a ordem correta.
    return sorted(arquivos, reverse=True)


def _rotacionar(pasta: str, motivo: str) -> int:
    limite = LIMITE_POR_MOTIVO.get(motivo, LIMITE_PADRAO)
    excedentes = _copias_existentes(pasta, motivo)[limite:]
    removidos = 0
    for caminho in excedentes:
        try:
            os.remove(caminho)
            removidos += 1
        except OSError:
            # Arquivo em uso ou permissao negada nao pode derrubar o boot:
            # a copia nova ja foi gravada, que e o que importa.
            log.warning("[BACKUP] Nao removeu copia antiga: %s", caminho)
    return removidos


def existe_backup_de_hoje(caminho_banco: str, motivo: str = MOTIVO_DIARIO) -> bool:
    hoje = time.strftime("%Y%m%d")
    marca = f"{PREFIXO}_{motivo}_{hoje}"
    return any(
        os.path.basename(caminho).startswith(marca)
        for caminho in _copias_existentes(pasta_de_backups(caminho_banco), motivo)
    )


def criar_backup(caminho_banco: str, motivo: str) -> Optional[str]:
    """
    Grava uma copia integra do banco e rotaciona as antigas.

    Devolve o caminho gravado, ou `None` quando nao havia o que copiar ou a
    copia falhou. **Nunca levanta**: backup e rede de seguranca, e derrubar a
    inicializacao do app por causa de disco cheio seria trocar um risco por
    um problema garantido.
    """
    if not os.path.exists(caminho_banco):
        return None

    pasta = pasta_de_backups(caminho_banco)
    destino = os.path.join(pasta, _nome_do_arquivo(motivo))
    origem = None
    copia = None
    try:
        os.makedirs(pasta, exist_ok=True)
        # `mode=ro` garante que o backup jamais escreva na origem.
        origem = sqlite3.connect(f"file:{caminho_banco}?mode=ro", uri=True, timeout=10)
        copia = sqlite3.connect(destino)
        with copia:
            origem.backup(copia)
        integridade = copia.execute("PRAGMA integrity_check").fetchone()[0]
        if integridade != "ok":
            raise sqlite3.DatabaseError(f"integrity_check devolveu '{integridade}'")
    except (sqlite3.Error, OSError) as erro:
        log.warning("[BACKUP] Falhou (%s): %s", motivo, erro)
        # Copia parcial e pior que copia nenhuma: da falsa seguranca.
        try:
            if copia is not None:
                copia.close()
                copia = None
            if os.path.exists(destino):
                os.remove(destino)
        except OSError:
            pass
        return None
    finally:
        for conexao in (origem, copia):
            if conexao is not None:
                try:
                    conexao.close()
                except sqlite3.Error:
                    pass

    _rotacionar(pasta, motivo)
    log.info("[BACKUP] %s -> %s", motivo, destino)
    return destino


def backup_diario(caminho_banco: str) -> Optional[str]:
    """Uma copia por dia, no maximo. Silencioso quando a do dia ja existe."""
    if existe_backup_de_hoje(caminho_banco, MOTIVO_DIARIO):
        return None
    return criar_backup(caminho_banco, MOTIVO_DIARIO)


def backup_antes_de_migrar(caminho_banco: str) -> Optional[str]:
    """Copia obrigatoria antes de mexer no schema."""
    return criar_backup(caminho_banco, MOTIVO_PRE_MIGRACAO)
