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
import shutil
import sqlite3
import tempfile
import time

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

# Segundo destino, opcional, definido pelo operador.
#
# Todas as copias moram ao lado do banco, no mesmo perfil e no mesmo disco. Isso
# cobre erro de operacao, migracao malsucedida e corrupcao de arquivo -- mas nao
# cobre o disco morrer, o computador ser roubado nem o ransomware, que cifra a
# pasta de backups junto com o resto.
#
# `ADRI_BACKUP_EXTRA` aponta para um pen drive, uma unidade de rede ou uma pasta
# do OneDrive. E deliberadamente opcional: ligar isso por padrao copiaria dados
# de clientes para um lugar que o operador nao escolheu.
VARIAVEL_DESTINO_EXTRA = "ADRI_BACKUP_EXTRA"


def pasta_de_backups(caminho_banco: str) -> str:
    """
    `backups/` ao lado do arquivo do banco.

    Segue o banco em vez de fixar %APPDATA%: assim a suite de testes, que
    aponta ADRI_DB_PATH para um diretorio temporario, nao escreve na pasta
    real do usuario.
    """
    return os.path.join(os.path.dirname(os.path.abspath(caminho_banco)), "backups")


def _nome_do_arquivo(motivo: str, momento: time.struct_time | None = None) -> str:
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


def criar_backup(caminho_banco: str, motivo: str) -> str | None:
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
    _copiar_para_destino_extra(destino)
    return destino


def _copiar_para_destino_extra(origem: str) -> str | None:
    """
    Duplica a copia num segundo lugar, quando o operador configurou um.

    Nunca levanta e nunca invalida o backup principal: se o pen drive nao esta
    conectado, a copia local ja esta gravada e e ela que importa.
    """
    destino_base = (os.environ.get(VARIAVEL_DESTINO_EXTRA) or "").strip()
    if not destino_base:
        return None
    try:
        os.makedirs(destino_base, exist_ok=True)
        destino = os.path.join(destino_base, os.path.basename(origem))
        shutil.copy2(origem, destino)
        log.info("[BACKUP] Copia externa -> %s", destino)
        return destino
    except OSError as erro:
        log.warning("[BACKUP] Copia externa falhou: %s", erro)
        return None


# =============================================================================
# Restauracao
#
# Ate aqui havia backup e nao havia volta: as copias existiam, e recuperar uma
# delas exigia fechar o app, achar a pasta em %APPDATA%, entender o nome dos
# arquivos e sobrescrever o banco na mao. Um backup sem procedimento de
# restauracao testado e uma suposicao, nao uma garantia.
# =============================================================================
def listar_copias(caminho_banco: str) -> list:
    """Copias disponiveis, da mais recente para a mais antiga."""
    pasta = pasta_de_backups(caminho_banco)
    copias = []
    for motivo in (MOTIVO_PRE_MIGRACAO, MOTIVO_DIARIO):
        for arquivo in _copias_existentes(pasta, motivo):
            try:
                tamanho = os.path.getsize(arquivo)
                modificado = os.path.getmtime(arquivo)
            except OSError:
                continue
            copias.append({
                "arquivo": os.path.basename(arquivo),
                "motivo": motivo,
                "bytes": tamanho,
                "criado_em": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(modificado)),
            })
    return sorted(copias, key=lambda c: c["arquivo"], reverse=True)


def caminho_da_copia(caminho_banco: str, nome_do_arquivo: str) -> str | None:
    """
    Resolve o nome de uma copia para o caminho dela, recusando qualquer coisa
    que nao seja um nome de arquivo simples.

    A checagem existe porque o nome chega pela API: sem ela, "..\\..\\Windows\\
    system32\\config\\SAM" seria um caminho valido e a restauracao viraria uma
    leitura arbitraria de arquivo.
    """
    nome = os.path.basename(nome_do_arquivo or "")
    if not nome or nome != nome_do_arquivo:
        return None
    if not nome.startswith(f"{PREFIXO}_") or not nome.endswith(".db"):
        return None
    caminho = os.path.join(pasta_de_backups(caminho_banco), nome)
    return caminho if os.path.isfile(caminho) else None


def copia_e_integra(caminho_copia: str) -> bool:
    """Confere que o arquivo abre e passa no integrity_check antes de usa-lo."""
    try:
        conexao = sqlite3.connect(f"file:{caminho_copia}?mode=ro", uri=True, timeout=10)
    except sqlite3.Error:
        return False
    try:
        return conexao.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    except sqlite3.Error:
        return False
    finally:
        conexao.close()


def restaurar(caminho_banco: str, caminho_copia: str) -> tuple[bool, str]:
    """
    Sobrescreve o banco atual com o conteudo de uma copia.

    Tres cuidados, nesta ordem:

    1. A copia e verificada ANTES de qualquer escrita. Restaurar de um arquivo
       corrompido trocaria um banco ruim por um pior.
    2. O estado atual e salvo como copia de pre-migracao. Restaurar tambem e
       uma operacao destrutiva: se o operador escolheu o arquivo errado, ele
       precisa de um caminho de volta.
    3. A troca usa a API `backup()` do SQLite, e nao substituicao de arquivo. A
       API escreve dentro de uma transacao e respeita o bloqueio -- trocar o
       arquivo por baixo de uma conexao aberta corromperia o banco.

    Devolve (deu_certo, mensagem).
    """
    if not os.path.isfile(caminho_copia):
        return False, "A copia informada nao foi encontrada."
    if not copia_e_integra(caminho_copia):
        return False, "A copia esta corrompida e nao pode ser restaurada."

    salvaguarda = criar_backup(caminho_banco, MOTIVO_PRE_MIGRACAO)
    if os.path.exists(caminho_banco) and not salvaguarda:
        return False, (
            "Nao foi possivel salvar o estado atual antes de restaurar. "
            "Verifique espaco em disco."
        )

    origem = None
    destino = None
    try:
        origem = sqlite3.connect(f"file:{caminho_copia}?mode=ro", uri=True, timeout=10)
        destino = sqlite3.connect(caminho_banco, timeout=10)
        with destino:
            origem.backup(destino)
    except sqlite3.Error as erro:
        log.exception("[BACKUP] Restauracao falhou")
        return False, f"Falha ao restaurar: {erro}"
    finally:
        for conexao in (origem, destino):
            if conexao is not None:
                try:
                    conexao.close()
                except sqlite3.Error:
                    pass

    log.warning("[BACKUP] Banco restaurado a partir de %s", caminho_copia)
    return True, (
        f"Banco restaurado a partir de {os.path.basename(caminho_copia)}. "
        f"O estado anterior foi guardado como {os.path.basename(salvaguarda)}."
        if salvaguarda else
        f"Banco restaurado a partir de {os.path.basename(caminho_copia)}."
    )


def copia_para_download(caminho_banco: str) -> str | None:
    """
    Copia integra e temporaria do banco, para o download manual.

    A rota de backup enviava o ARQUIVO EM USO direto pelo `send_file`. Com o
    app aberto isso captura um estado no meio de uma transacao e deixa de fora
    o que estiver no `-wal` -- o operador baixava um arquivo que parecia um
    backup e podia nao abrir. Aqui vale a mesma regra do backup automatico:
    `Connection.backup()`, com `integrity_check` antes de entregar.

    O nome vem do `mkstemp`, e nao do relogio. Derivado do horario ele era
    adivinhavel -- `adri_poltronas_download_AAAAMMDD_HHMMSS.db` -- e o arquivo
    e o banco INTEIRO, com nome, endereco e dados financeiros de todos os
    clientes. O blueprint apaga logo depois de ler, mas ha uma janela, e nela
    outro processo do mesmo usuario podia abrir o arquivo sabendo o nome de
    antemao. O `mkstemp` sorteia o sufixo e cria com permissao restrita ao
    dono, fechando a janela sem custo nenhum.
    """
    if not os.path.exists(caminho_banco):
        return None

    # O descritor e fechado de imediato: quem escreve no arquivo e o
    # `sqlite3.connect` abaixo, que precisa abrir o caminho por conta propria.
    # O que o mkstemp entrega e o nome imprevisivel e o arquivo ja existente,
    # o que impede outro processo de vencer a corrida criando-o antes.
    descritor, destino = tempfile.mkstemp(prefix=f"{PREFIXO}_download_", suffix=".db")
    os.close(descritor)

    origem = None
    copia = None
    try:
        origem = sqlite3.connect(f"file:{caminho_banco}?mode=ro", uri=True, timeout=10)
        copia = sqlite3.connect(destino)
        with copia:
            origem.backup(copia)
        if copia.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise sqlite3.DatabaseError("integrity_check falhou na copia para download")
    except (sqlite3.Error, OSError) as erro:
        log.warning("[BACKUP] Copia para download falhou: %s", erro)
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
    return destino


def backup_diario(caminho_banco: str) -> str | None:
    """Uma copia por dia, no maximo. Silencioso quando a do dia ja existe."""
    if existe_backup_de_hoje(caminho_banco, MOTIVO_DIARIO):
        return None
    return criar_backup(caminho_banco, MOTIVO_DIARIO)


def backup_antes_de_migrar(caminho_banco: str) -> str | None:
    """Copia obrigatoria antes de mexer no schema."""
    return criar_backup(caminho_banco, MOTIVO_PRE_MIGRACAO)
