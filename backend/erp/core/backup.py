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

CIFRA EM REPOUSO
A copia sai cifrada com Fernet, e a chave do Fernet vive protegida pelo DPAPI
da conta do Windows (`backend/security.py`). O motivo e o destino desses
arquivos: sao as copias que SAEM da pasta do banco -- `ADRI_BACKUP_EXTRA` as
leva para pendrive, pasta sincronizada ou unidade de rede, e um pendrive com
o banco inteiro dos clientes dentro do bolso e o vazamento que nenhuma
outra camada deste sistema consegue desfazer.

O preco e honesto e precisa estar escrito: a copia so abre na MESMA conta
do Windows que a gravou. Restaurar em outra maquina ou outra conta exige
reimportar o banco pelo download explicito (`/api/backup/sqlite`, que sai em
claro por ser uma exportacao deliberada do operador -- mesma natureza do
backup JSON de clientes).

Sem fonte de chave (desenvolvimento fora do Windows sem `FERNET_KEY`), a
copia e gravada em claro e o log avisa: backup existente vale mais que
backup que nao existe. Copias de versoes anteriores, gravadas em claro,
continuam restauraveis -- o marcador `ADRIBKP1:` no inicio do arquivo e o
que distingue as duas especies.
"""
from __future__ import annotations

import logging
import os
import shutil
import sqlite3
import tempfile
import time

import security

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

# Senha que cifra a copia do segundo destino.
#
# A copia local e cifrada com uma chave presa a conta do Windows -- e a copia
# externa, ate a 1.5.2, era um duplicado dela. So que a copia externa existe
# justamente para o dia em que o computador nao existe mais, e nesse dia a
# chave foi junto: o pendrive guardava um arquivo que ninguem conseguia abrir.
#
# Com a senha definida, a copia externa e cifrada com ela e abre em qualquer
# maquina. Sem a senha, o comportamento antigo e mantido (duplicado da copia
# local) e o log diz, a cada copia, que ela so serve nesta conta.
VARIAVEL_SENHA_DAS_COPIAS = "ADRI_BACKUP_SENHA"


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


def _conteudo_cifrado(caminho: str) -> str | None:
    """
    Le o arquivo e devolve o conteudo cifrado, ou None sem fonte de chave.

    O None nao e erro: e o modo de desenvolvimento fora do Windows sem
    `FERNET_KEY`. Nesse estado a copia em claro e gravada com aviso no log,
    porque a alternativa -- falhar o backup -- trocaria uma protecao
    ausente por um backup inexistente, que e pior.
    """
    try:
        with open(caminho, "rb") as arquivo:
            claro = arquivo.read()
        return security.cifrar_bytes(claro)
    except RuntimeError as erro:
        log.warning("[BACKUP] Cifra indisponivel; copia gravada EM CLARO: %s", erro)
        return None


def _marcador(caminho: str) -> str:
    """Os primeiros bytes do arquivo, onde mora o marcador da especie."""
    tamanho = max(len(security.MAGICO_BYTES), len(security.MAGICO_BYTES_SENHA))
    try:
        with open(caminho, "rb") as arquivo:
            return arquivo.read(tamanho).decode("ascii", errors="replace")
    except OSError:
        return ""


def _portatil(caminho: str) -> bool:
    """A copia foi cifrada com a senha das copias (abre em qualquer maquina)?"""
    return _marcador(caminho).startswith(security.MAGICO_BYTES_SENHA)


def _cifrada(caminho: str) -> bool:
    """A copia carrega um marcador de conteudo cifrado, de qualquer especie?"""
    marcador = _marcador(caminho)
    return (marcador.startswith(security.MAGICO_BYTES)
            or marcador.startswith(security.MAGICO_BYTES_SENHA))


def senha_das_copias() -> str:
    """
    A senha das copias portateis, ou vazio quando nao ha uma utilizavel.

    Vem do cofre cifrado (ou do `.env`, de onde e migrada para o cofre no
    boot). Senha curta demais conta como ausente: cifrar com ela daria ao
    operador a impressao de protecao num arquivo que se abre por tentativa.
    """
    import segredos

    senha = (segredos.obter(VARIAVEL_SENHA_DAS_COPIAS) or "").strip()
    return senha if security.senha_de_backup_valida(senha) else ""


def _materializar_copia(caminho_copia: str) -> str | None:
    """
    Caminho legivel como SQLite para a copia, cifrada ou nao.

    Copia em claro (legado, ou dev sem chave): o proprio caminho. Copia
    cifrada: um arquivo temporario decifrado, que QUEM CHAMA apaga depois.

    None significa ilegivel: ou a chave nao decifra (outra conta do
    Windows, arquivo adulterado) ou o conteudo nao e banco nenhum. As duas
    respostas proibem a restauracao -- copia de seguranca que nao abre e
    tao boa quanto nao existir, e fingir o contrario seria pior.
    """
    if not _cifrada(caminho_copia):
        return caminho_copia

    try:
        with open(caminho_copia, encoding="ascii", errors="strict") as arquivo:
            conteudo = arquivo.read()
    except (OSError, UnicodeDecodeError):
        return None

    if conteudo.startswith(security.MAGICO_BYTES_SENHA):
        # Copia portatil: quem abre e a senha das copias, nao a conta do
        # Windows. E o caminho da recuperacao em outro computador.
        claro = security.decifrar_bytes_com_senha(conteudo, senha_das_copias())
    else:
        claro = security.decifrar_bytes(conteudo)
    if claro is None:
        return None

    descritor, caminho = tempfile.mkstemp(prefix=f"{PREFIXO}_restauracao_", suffix=".db")
    try:
        with os.fdopen(descritor, "wb") as arquivo:
            arquivo.write(claro)
    except OSError:
        try:
            os.remove(caminho)
        except OSError:
            pass
        return None
    return caminho


def criar_backup(caminho_banco: str, motivo: str) -> str | None:
    """
    Grava uma copia integra e cifrada do banco e rotaciona as antigas.

    Devolve o caminho gravado, ou `None` quando nao havia o que copiar ou a
    copia falhou. **Nunca levanta**: backup e rede de seguranca, e derrubar a
    inicializacao do app por causa de disco cheio seria trocar um risco por
    um problema garantido.
    """
    if not os.path.exists(caminho_banco):
        return None

    pasta = pasta_de_backups(caminho_banco)
    destino = os.path.join(pasta, _nome_do_arquivo(motivo))
    # A copia inteira nasce com outro nome e so entao assume o definitivo:
    # um arquivo com cara de backup e conteudo pela metade e a mentira mais
    # cara que esta pasta pode guardar.
    trabalho = destino + ".parcial"
    origem = None
    copia = None
    try:
        os.makedirs(pasta, exist_ok=True)
        # `mode=ro` garante que o backup jamais escreva na origem.
        origem = sqlite3.connect(f"file:{caminho_banco}?mode=ro", uri=True, timeout=10)
        copia = sqlite3.connect(trabalho)
        with copia:
            origem.backup(copia)
        integridade = copia.execute("PRAGMA integrity_check").fetchone()[0]
        if integridade != "ok":
            raise sqlite3.DatabaseError(f"integrity_check devolveu '{integridade}'")
        copia.close()
        copia = None

        # Lido uma vez, em memoria, para a copia externa: ela pode precisar do
        # conteudo em claro para cifrar com a senha, e depois deste bloco o
        # arquivo de trabalho ja nao existe.
        with open(trabalho, "rb") as arquivo:
            claro = arquivo.read()

        cifrado = _conteudo_cifrado(trabalho)
        if cifrado is not None:
            with open(destino, "w", encoding="ascii", newline="") as arquivo:
                arquivo.write(cifrado)
        else:
            os.replace(trabalho, destino)
    except (sqlite3.Error, OSError) as erro:
        log.warning("[BACKUP] Falhou (%s): %s", motivo, erro)
        # Copia parcial e pior que copia nenhuma: da falsa seguranca.
        try:
            if copia is not None:
                copia.close()
                copia = None
            for sobra in (trabalho, destino):
                if os.path.exists(sobra):
                    os.remove(sobra)
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
        try:
            if os.path.exists(trabalho):
                os.remove(trabalho)
        except OSError:
            pass

    _rotacionar(pasta, motivo)
    log.info("[BACKUP] %s -> %s%s", motivo, destino,
             " (cifrada)" if _cifrada(destino) else "")
    _copiar_para_destino_extra(destino, claro)
    return destino


def _copiar_para_destino_extra(origem: str, claro: bytes | None = None) -> str | None:
    """
    Leva a copia a um segundo lugar, quando o operador configurou um.

    Com a senha das copias definida, o que vai e uma copia PORTATIL: cifrada
    com a senha, abre em qualquer computador. Sem ela vai um duplicado da
    copia local, que so abre nesta conta do Windows -- e o log diz isso com
    todas as letras, porque e a diferenca entre ter e nao ter de onde
    recuperar quando a maquina se perde.

    Nunca levanta e nunca invalida o backup principal: se o pen drive nao esta
    conectado, a copia local ja esta gravada e e ela que importa.
    """
    destino_base = (os.environ.get(VARIAVEL_DESTINO_EXTRA) or "").strip()
    if not destino_base:
        return None

    destino = os.path.join(destino_base, os.path.basename(origem))
    senha = senha_das_copias()
    try:
        os.makedirs(destino_base, exist_ok=True)
        if senha and claro is not None:
            # Nasce com outro nome e so entao assume o definitivo, como a
            # copia local: pendrive arrancado no meio da escrita nao pode
            # deixar um arquivo com cara de backup e conteudo pela metade.
            parcial = destino + ".parcial"
            with open(parcial, "w", encoding="ascii", newline="") as arquivo:
                arquivo.write(security.cifrar_bytes_com_senha(claro, senha))
            os.replace(parcial, destino)
            log.info("[BACKUP] Copia externa portatil (cifrada com a senha das "
                     "copias) -> %s", destino)
        else:
            shutil.copy2(origem, destino)
            log.warning(
                "[BACKUP] Copia externa -> %s. ATENCAO: sem %s definida, esta "
                "copia so abre NESTA conta do Windows -- se o computador se "
                "perder, ela nao recupera nada. Defina uma senha de ao menos "
                "%s caracteres e guarde-a fora deste computador.",
                destino, VARIAVEL_SENHA_DAS_COPIAS,
                security.TAMANHO_MINIMO_SENHA_DE_BACKUP,
            )
        return destino
    except (OSError, ValueError) as erro:
        log.warning("[BACKUP] Copia externa falhou: %s", erro)
        try:
            if os.path.exists(destino + ".parcial"):
                os.remove(destino + ".parcial")
        except OSError:
            pass
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
                # A copia cifrada so abre nesta conta do Windows -- e melhor
                # que a lista diga isso ANTES de o operador escolher uma.
                "cifrada": _cifrada(arquivo),
                # Portatil = cifrada com a senha das copias; e a que veio de
                # um pendrive e abre aqui mesmo tendo sido gravada em outro
                # computador.
                "portatil": _portatil(arquivo),
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
    """
    Confere que o arquivo abre e passa no integrity_check antes de usa-lo.

    A copia pode chegar cifrada: decifra para um temporario, verifica o
    conteudo e apaga o claro em seguida -- o material decifrado nao pode
    sobreviver na pasta temporaria depois da resposta.
    """
    legivel = _materializar_copia(caminho_copia)
    if legivel is None:
        return False
    try:
        conexao = sqlite3.connect(f"file:{legivel}?mode=ro", uri=True, timeout=10)
    except sqlite3.Error:
        return False
    try:
        return conexao.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    except sqlite3.Error:
        return False
    finally:
        conexao.close()
        if legivel != caminho_copia:
            try:
                os.remove(legivel)
            except OSError:
                pass


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

    Copia cifrada vira arquivo claro num temporario, usado como origem e
    apagado no fim. A chave que decifra e a da conta do Windows atual: uma
    copia levada para outra conta aparece aqui como ilegivel, e a mensagem
    diz isso em vez de chamar de corrupcao -- sao dois problemas com
    solucoes diferentes.

    Devolve (deu_certo, mensagem).
    """
    if not os.path.isfile(caminho_copia):
        return False, "A copia informada nao foi encontrada."

    legivel = _materializar_copia(caminho_copia)
    if legivel is None:
        if _portatil(caminho_copia):
            # Sao dois problemas com solucoes diferentes, e a mensagem
            # precisa dizer qual: aqui o que falta e a senha, nao a conta.
            return False, (
                "A copia e protegida pela senha das copias e nao pode ser "
                f"aberta: defina {VARIAVEL_SENHA_DAS_COPIAS} com a mesma senha "
                "usada quando ela foi gravada e reabra o aplicativo."
            )
        return False, (
            "A copia nao pode ser lida: ela foi gravada com a cifra de outra "
            "conta do Windows, ou o arquivo foi adulterado."
        )
    temporario = legivel if legivel != caminho_copia else None

    try:
        if not copia_e_integra(legivel):
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
            origem = sqlite3.connect(f"file:{legivel}?mode=ro", uri=True, timeout=10)
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
    finally:
        # O claro decifrado nao sobrevive a restauracao: e um banco inteiro
        # na pasta temporaria, e a copia cifrada e a que vale guardar.
        if temporario:
            try:
                os.remove(temporario)
            except OSError:
                pass


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

    Sai EM CLARO, de proposito, enquanto as copias automaticas saem
    cifradas: esta e uma exportacao que o operador pediu, para guardar onde
    ele escolher -- cifrar com a chave da conta atual a prendia a esta
    maquina, e o objetivo do download e justamente sair dela. O preco e o
    mesmo do backup JSON: quem baixa assume o arquivo.
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
