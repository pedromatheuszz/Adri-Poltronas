"""
Módulo de segurança completo: criptografia, CSRF, sessões, sanitização, hashing.

Em Windows, usa DPAPI (Data Protection API) através de `win32crypt` —
proteção ligada à conta de usuário do SO. Nenhuma chave precisa ser
armazenada: o Windows deriva a chave do logon do usuário.

Adicionalmente usa Fernet (AES-128-CBC + HMAC-SHA256) da biblioteca
cryptography para criptografia simétrica de dados sensíveis em repouso.

Em outras plataformas (apenas para dev fora do app empacotado), usa
base64 + flag de marcação para deixar claro que NÃO está cifrado.
Em produção (PyInstaller), o fallback PLAIN é recusado por segurança.
"""
import base64
import sys
import os
import secrets
import json
import logging
from typing import Any

from cryptography.fernet import Fernet

# O DPAPI (win32crypt) só existe no Windows e é importado sob demanda por
# _importar_win32crypt(), definida abaixo.

PREFIXO_DPAPI = "DPAPI1:"
PREFIXO_PLAIN = "PLAIN1:"
PREFIXO_FERNET = "FERN1:"

PRODUCAO = bool(getattr(sys, 'frozen', False))

log = logging.getLogger("adri.security")

_fernet_key_cache: bytes | None = None

def _obter_chave_fernet() -> bytes:
    """
    Retorna a chave Fernet validada.
    Tenta ler FERNET_KEY do ambiente; se não existir, usa DPAPI para
    recuperar/criar uma chave persistente no sistema operacional.
    A chave é cacheada em memória para evitar regeneração.
    """
    global _fernet_key_cache
    if _fernet_key_cache is not None:
        return _fernet_key_cache

    env_key = os.environ.get('FERNET_KEY', '')
    if env_key:
        try:
            Fernet(env_key.encode())
            _fernet_key_cache = env_key.encode()
            return _fernet_key_cache
        except Exception:
            log.warning("[FERNET] FERNET_KEY invalida, gerando nova chave.")

    win32 = _importar_win32crypt()
    if win32:
        storage_path = os.path.join(
            os.environ.get("APPDATA", os.getcwd()),
            "AdriPoltronas", ".fernet_key"
        )
        try:
            os.makedirs(os.path.dirname(storage_path), exist_ok=True)
        except OSError:
            pass
        if os.path.exists(storage_path):
            try:
                with open(storage_path) as f:
                    stored = f.read().strip()
                decrypted = win32.CryptUnprotectData(
                    base64.b64decode(stored), None, None, None, 0
                )
                _fernet_key_cache = decrypted[1]
                return _fernet_key_cache
            except Exception:
                # A chave gravada nao abre nesta conta agora -- senha do
                # Windows redefinida por um administrador, perfil migrado,
                # arquivo trazido de outra maquina. Antes isto so avisava e
                # seguia: a chave nova era gravada POR CIMA da antiga, e
                # todas as copias de seguranca cifradas com ela viravam
                # irrecuperaveis para sempre, mesmo que o motivo fosse
                # passageiro. A antiga agora e posta de lado, intacta: se o
                # DPAPI voltar a abri-la, as copias antigas voltam junto.
                guardada = _por_chave_ilegivel_de_lado(storage_path)
                log.error(
                    "[FERNET] A chave das copias de seguranca nao pode ser lida "
                    "nesta conta do Windows. As copias cifradas anteriores NAO "
                    "abrem com a chave nova. Chave antiga preservada em: %s",
                    guardada or "(nao foi possivel preservar; arquivo mantido)",
                )
                if guardada is None:
                    # Sem conseguir tirar a antiga do caminho, gravar a nova a
                    # destruiria. Recusar e o unico desfecho que nao perde nada.
                    raise RuntimeError(
                        "A chave de cifragem existente esta ilegivel e nao pode "
                        "ser preservada; nenhuma chave nova foi gravada."
                    ) from None

        nova_chave = Fernet.generate_key()
        cifrado = win32.CryptProtectData(nova_chave, None, None, None, None, 0)
        try:
            with open(storage_path, 'w') as f:
                f.write(base64.b64encode(cifrado).decode('ascii'))
        except OSError:
            log.warning("[FERNET] Nao foi possivel salvar chave persistente.")
        _fernet_key_cache = nova_chave
        return _fernet_key_cache

    raise RuntimeError(
        "Nenhuma fonte de chave Fernet disponivel. "
        "Defina FERNET_KEY ou use Windows com DPAPI."
    )


def _por_chave_ilegivel_de_lado(caminho: str) -> str | None:
    """
    Renomeia a chave que nao abre, sem apaga-la. Devolve o novo caminho.

    O nome leva data e hora: se isto acontecer duas vezes, a segunda nao pode
    passar por cima da primeira.
    """
    import time

    destino = f"{caminho}.ilegivel-{time.strftime('%Y%m%d-%H%M%S')}"
    try:
        os.replace(caminho, destino)
        return destino
    except OSError:
        return None


def _get_fernet() -> Fernet:
    return Fernet(_obter_chave_fernet())


def _importar_win32crypt():
    if not sys.platform.startswith("win"):
        return None
    try:
        import win32crypt
        return win32crypt
    except ImportError:
        return None


# ---------------------------------------------------------------------------
# Criptografia DPAPI (existente, backward compatible)
# ---------------------------------------------------------------------------

def cifrar(texto: str) -> str:
    if texto is None:
        return ""
    if not isinstance(texto, str):
        texto = str(texto)

    wc = _importar_win32crypt()
    if wc is not None:
        dados = texto.encode("utf-8")
        cifrado = wc.CryptProtectData(dados, None, None, None, None, 0)
        return PREFIXO_DPAPI + base64.b64encode(cifrado).decode("ascii")

    if PRODUCAO:
        raise RuntimeError(
            "DPAPI indisponivel em ambiente de producao. "
            "Cifragem de segredos abortada para nao expor o token."
        )

    log.warning(
        "[security] Cifrando em modo PLAINTEXT (apenas dev). Nao use em producao."
    )
    return PREFIXO_PLAIN + base64.b64encode(texto.encode("utf-8")).decode("ascii")


def decifrar(valor: str):
    if not valor:
        return None

    if valor.startswith(PREFIXO_DPAPI):
        wc = _importar_win32crypt()
        if wc is None:
            return None
        # O b64decode fica DENTRO do try: um valor truncado ou editado a mao
        # levanta binascii.Error, e essa excecao escapava daqui. Quem chama
        # espera `None` para "nao consegui decifrar" -- um arquivo corrompido
        # derrubava a leitura inteira em vez de degradar.
        try:
            bruto = base64.b64decode(valor[len(PREFIXO_DPAPI):])
            resultado = wc.CryptUnprotectData(bruto, None, None, None, 0)
            return resultado[1].decode("utf-8")
        except Exception:
            return None

    if valor.startswith(PREFIXO_PLAIN):
        if PRODUCAO:
            log.error(
                "[security] Valor PLAINTEXT encontrado em producao. "
                "Recusando decifrar para evitar exposicao."
            )
            return None
        try:
            return base64.b64decode(valor[len(PREFIXO_PLAIN):]).decode("utf-8")
        except Exception:
            return None

    if PRODUCAO:
        log.error(
            "[security] Valor sem prefixo de cifragem em producao. "
            "Recusando para evitar exposicao de segredo em texto claro."
        )
        return None
    return valor


def migrar_para_cifrado(valor: str) -> str:
    if not valor:
        return valor
    if valor.startswith((PREFIXO_DPAPI, PREFIXO_PLAIN)):
        if valor.startswith(PREFIXO_PLAIN):
            claro = decifrar(valor) or ""
            return cifrar(claro)
        return valor
    return cifrar(valor)


# ---------------------------------------------------------------------------
# Criptografia Fernet (camada adicional para dados sensíveis em repouso)
# ---------------------------------------------------------------------------

def fernet_cifrar(texto: str) -> str:
    """Cifra uma string com Fernet (AES-128-CBC + HMAC-SHA256)."""
    if not texto:
        return ""
    f = _get_fernet()
    dado = texto.encode("utf-8")
    return PREFIXO_FERNET + f.encrypt(dado).decode("ascii")


def fernet_decifrar(valor: str) -> str | None:
    """Decifra um valor Fernet. Retorna None se invalido."""
    if not valor or not valor.startswith(PREFIXO_FERNET):
        return None
    try:
        f = _get_fernet()
        # O token Fernet JA e base64 url-safe -- e o que `encrypt()` devolve.
        # Passa-lo por base64.b64decode antes do decrypt() destruia o valor
        # duas vezes: um decode a mais, e o alfabeto url-safe ('-' e '_') nao
        # sobrevive ao base64 padrao. Nenhum round-trip fechava, e o fallback
        # de sessao em obter_sessao() nunca teve como funcionar.
        token = valor[len(PREFIXO_FERNET):].encode("ascii")
        return f.decrypt(token).decode("utf-8")
    except Exception:
        log.warning("[FERNET] Falha ao decifrar valor.")
        return None


def fernet_cifrar_objeto(objeto: Any) -> str:
    """Cifra um objeto Python serializado como JSON com Fernet."""
    json_str = json.dumps(objeto, ensure_ascii=False, separators=(',', ':'))
    return fernet_cifrar(json_str)


def fernet_decifrar_objeto(valor: str) -> Any | None:
    """Decifra e deserializa um objeto JSON Fernet."""
    json_str = fernet_decifrar(valor)
    if json_str is None:
        return None
    try:
        return json.loads(json_str)
    except (json.JSONDecodeError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Bytes inteiros: copias de seguranca
# ---------------------------------------------------------------------------
# O Fernet cifra bytes de qualquer tamanho num so token, e a copia do banco e
# pequena (centenas de KB). Este par existe para que `backup.py` nao precise
# improvisar codificacao de texto sobre as funcoes de string: o arquivo do
# banco e binario, e trata-lo como texto o corromperia no primeiro byte fora
# de ASCII.
MAGICO_BYTES = "ADRIBKP1:"


def cifrar_bytes(dados: bytes) -> str:
    """Cifra bytes com Fernet, com o marcador da especie de conteudo."""
    if not isinstance(dados, (bytes, bytearray)):
        raise ValueError("cifrar_bytes espera bytes.")
    return MAGICO_BYTES + _get_fernet().encrypt(bytes(dados)).decode("ascii")


def decifrar_bytes(valor: str) -> bytes | None:
    """Decifra o que `cifrar_bytes` produziu. None quando ilegivel."""
    if not valor or not isinstance(valor, str) or not valor.startswith(MAGICO_BYTES):
        return None
    try:
        return _get_fernet().decrypt(valor[len(MAGICO_BYTES):].encode("ascii"))
    except Exception:
        log.warning("[FERNET] Falha ao decifrar bytes.")
        return None


def bytes_estao_cifrados(valor: str) -> bool:
    """True quando o conteudo carrega o marcador de copia cifrada."""
    return isinstance(valor, str) and valor.startswith(MAGICO_BYTES)


# ---------------------------------------------------------------------------
# Copia portatil: cifrada com senha, e nao com a conta do Windows
# ---------------------------------------------------------------------------
# A chave acima vive em `.fernet_key`, protegida pelo DPAPI: morre junto com a
# maquina. Isso e o que se quer para a copia que fica ao lado do banco, e o
# contrario do que se quer para a copia que vai para o pendrive -- ela existe
# para o dia em que o computador e roubado ou o disco para, e nesse dia a
# chave ja nao existe.
#
# A copia portatil e cifrada com uma chave derivada de uma senha que o
# operador escolhe e guarda fora do computador. Abre em qualquer maquina que
# tenha o arquivo e a senha; sem a senha, e tao opaca quanto a outra.
MAGICO_BYTES_SENHA = "ADRIBKP2:"
TAMANHO_MINIMO_SENHA_DE_BACKUP = 12

# scrypt, e nao um hash simples: a senha e escolhida por uma pessoa, e quem
# acha o pendrive pode tentar adivinhar offline, sem limite de tentativas.
# Estes parametros custam ~32 MB e uma fracao de segundo por tentativa -- nada
# para quem abre uma copia, caro para quem testa bilhoes.
_SCRYPT_N = 2 ** 15
_SCRYPT_R = 8
_SCRYPT_P = 1
_BYTES_DO_SAL = 16


def senha_de_backup_valida(senha: str | None) -> bool:
    return isinstance(senha, str) and len(senha.strip()) >= TAMANHO_MINIMO_SENHA_DE_BACKUP


def _chave_da_senha(senha: str, sal: bytes) -> bytes:
    from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

    derivada = Scrypt(salt=sal, length=32, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P)
    return base64.urlsafe_b64encode(derivada.derive(senha.strip().encode("utf-8")))


def cifrar_bytes_com_senha(dados: bytes, senha: str) -> str:
    """Cifra bytes com uma chave derivada da senha. O sal vai no arquivo."""
    if not isinstance(dados, (bytes, bytearray)):
        raise ValueError("cifrar_bytes_com_senha espera bytes.")
    if not senha_de_backup_valida(senha):
        raise ValueError(
            f"A senha das copias precisa de ao menos "
            f"{TAMANHO_MINIMO_SENHA_DE_BACKUP} caracteres."
        )
    sal = os.urandom(_BYTES_DO_SAL)
    cifrado = Fernet(_chave_da_senha(senha, sal)).encrypt(bytes(dados))
    return (MAGICO_BYTES_SENHA + base64.urlsafe_b64encode(sal).decode("ascii")
            + ":" + cifrado.decode("ascii"))


def decifrar_bytes_com_senha(valor: str, senha: str | None) -> bytes | None:
    """Decifra o que `cifrar_bytes_com_senha` produziu. None quando ilegivel
    -- senha errada, senha ausente ou arquivo adulterado dao a mesma resposta."""
    if not isinstance(valor, str) or not valor.startswith(MAGICO_BYTES_SENHA):
        return None
    if not senha_de_backup_valida(senha):
        return None
    try:
        sal_b64, _, cifrado = valor[len(MAGICO_BYTES_SENHA):].partition(":")
        sal = base64.urlsafe_b64decode(sal_b64.encode("ascii"))
        return Fernet(_chave_da_senha(senha, sal)).decrypt(cifrado.encode("ascii"))
    except Exception:
        log.warning("[FERNET] Falha ao decifrar copia protegida por senha.")
        return None


# Aqui viviam `hash_senha` e `verificar_senha` (PBKDF2-HMAC-SHA256, 600 mil
# iteracoes). Sairam pelo mesmo criterio que tirou os outros 40% deste
# modulo: nenhuma rota as chamava.
#
# Elas tinham sobrevivido a limpeza anterior por um motivo que deixou de
# valer. A auditoria as apontava como a peca pronta para o degrau 2 do
# SEG-01 -- identidade propria do ERP, em vez de reaproveitar o OAuth da
# Microsoft como identidade. Esse degrau foi descartado junto com a decisao
# de congelar o escopo do produto.
#
# Criptografia forte que ninguem chama nao protege nada; so sugere ao
# proximo leitor que existe login local. Se a identidade propria voltar a
# ser prioridade, o codigo esta no historico (`git log -S hash_senha`), e
# reescreve-lo custa menos do que o risco de mante-lo vivo e sem exercicio.
# ---------------------------------------------------------------------------
# Seguranca de Upload de Arquivos
# ---------------------------------------------------------------------------

# `.xls` FICOU DE FORA de proposito. O leitor usado na importacao e o
# openpyxl, que so abre o formato OOXML (.xlsx) -- entregar um .xls a ele
# levanta excecao. Aceitar a extensao aqui fazia a interface prometer um
# suporte que nao existe: o usuario escolhia o arquivo, aguardava, e recebia
# "nao foi possivel ler o arquivo enviado" sem saber por que.
_EXTENSOES_PERMITIDAS = {'.csv', '.json', '.xlsx'}
_TAMANHO_MAXIMO_UPLOAD = 10 * 1024 * 1024  # 10 MB
_MIME_TYPES_PERMITIDOS = {
    'text/csv',
    'application/json',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'application/vnd.ms-excel',
}


def _medir_sem_ler(arquivo) -> int:
    """
    Tamanho do arquivo pelo ponteiro, sem materializar o conteudo.

    Media-lo com `len(arquivo.read())` carregava os 10 MB inteiros em memoria
    so para descobrir quantos bytes eram -- e o parser logo em seguida lia tudo
    de novo. Duas copias completas do arquivo antes de qualquer validacao de
    conteudo.

    `seek(0, SEEK_END)` faz o mesmo trabalho sem alocar nada. O `finally`
    devolve o ponteiro ao inicio: sem isso o parser leria a partir do fim e
    encontraria um arquivo vazio.
    """
    if not hasattr(arquivo, 'seek') or not hasattr(arquivo, 'tell'):
        # Duble de teste sem ponteiro. Cai para a leitura, que ai e barata.
        return len(arquivo.read()) if hasattr(arquivo, 'read') else 0
    try:
        arquivo.seek(0, os.SEEK_END)
        return arquivo.tell()
    finally:
        arquivo.seek(0)


def validar_upload(arquivo, max_size: int = _TAMANHO_MAXIMO_UPLOAD) -> tuple:
    """
    Valida um arquivo uploadado. Retorna (valido: bool, erro: str ou None).
    """
    if arquivo is None:
        return False, "Nenhum arquivo fornecido."

    tamanho = _medir_sem_ler(arquivo)

    if tamanho > max_size:
        return False, f"Arquivo excede o tamanho maximo de {max_size // (1024*1024)}MB."

    if tamanho == 0:
        return False, "Arquivo vazio."

    filename = getattr(arquivo, 'filename', '')
    if not filename:
        return False, "Nome de arquivo invalido."

    ext = os.path.splitext(filename)[1].lower()
    if ext == '.xls':
        # O erro mais provavel de todos, e o unico que merece instrucao
        # propria: quem tem uma planilha antiga nao sabe que ela e de outro
        # formato, so que "o Excel abre". Mandar converter e mais util do que
        # informar que a extensao nao e permitida.
        return False, ("Arquivos .xls (Excel antigo) nao sao suportados. Abra a "
                       "planilha no Excel e salve como .xlsx, ou exporte para CSV.")
    if ext not in _EXTENSOES_PERMITIDAS:
        return False, f"Extensao nao permitida: {ext}. Use CSV, JSON ou XLSX."

    content_type = getattr(arquivo, 'content_type', '')
    if content_type and content_type not in _MIME_TYPES_PERMITIDOS:
        log.warning("[UPLOAD] MIME type suspeito: %s para %s", content_type, filename)

    return True, None


# ---------------------------------------------------------------------------
# Gerador de Tokens Seguros
# ---------------------------------------------------------------------------

def gerar_token_seguro(comprimento: int = 32) -> str:
    """Gera um token criptograficamente seguro."""
    return secrets.token_urlsafe(comprimento)


def gerar_id_unico() -> str:
    """Gera um ID unico usando UUID."""
    import uuid
    return uuid.uuid4().hex


# ---------------------------------------------------------------------------
# Log de Eventos de Seguranca
# ---------------------------------------------------------------------------

def log_evento_seguro(acao: str, detalhes: str, nivel: str = "info"):
    """Registra um evento de seguranca de forma consistente."""
    logger = getattr(log, nivel, log.info)
    logger("[SECURITY] %s: %s", acao, detalhes)
