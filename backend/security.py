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
import hmac
import secrets
import json
import logging
from typing import Optional, Any

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

# O DPAPI (win32crypt) só existe no Windows e é importado sob demanda por
# _importar_win32crypt(), definida abaixo.

PREFIXO_DPAPI = "DPAPI1:"
PREFIXO_PLAIN = "PLAIN1:"
PREFIXO_FERNET = "FERN1:"

PRODUCAO = bool(getattr(sys, 'frozen', False))

log = logging.getLogger("adri.security")

_fernet_key_cache: Optional[bytes] = None

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
                with open(storage_path, 'r') as f:
                    stored = f.read().strip()
                decrypted = win32.CryptUnprotectData(
                    base64.b64decode(stored), None, None, None, 0
                )
                _fernet_key_cache = decrypted[1]
                return _fernet_key_cache
            except Exception:
                log.warning("[FERNET] Falha ao recuperar chave, gerando nova.")

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


def fernet_decifrar(valor: str) -> Optional[str]:
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


def fernet_decifrar_objeto(valor: str) -> Optional[Any]:
    """Decifra e deserializa um objeto JSON Fernet."""
    json_str = fernet_decifrar(valor)
    if json_str is None:
        return None
    try:
        return json.loads(json_str)
    except (json.JSONDecodeError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Hashing seguro (PBKDF2-HMAC-SHA256)
# ---------------------------------------------------------------------------

def hash_senha(senha: str, salt: Optional[bytes] = None) -> str:
    """
    Gera hash PBKDF2-HMAC-SHA256 da senha.
    Retorna string formatada: algorithm$iterations$salt$hash
    """
    if salt is None:
        salt = os.urandom(32)

    iterations = 600_000
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=iterations,
    )
    hash_bytes = kdf.derive(senha.encode("utf-8"))
    return f"pbkdf2_sha256${iterations}${salt.hex()}${hash_bytes.hex()}"


def verificar_senha(senha: str, hash_armazenado: str) -> bool:
    """Verifica se uma senha corresponde ao hash armazenado."""
    try:
        parts = hash_armazenado.split("$")
        if len(parts) != 4 or parts[0] != "pbkdf2_sha256":
            return False
        iterations = int(parts[1])
        salt = bytes.fromhex(parts[2])
        hash_esperado = parts[3]

        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=iterations,
        )
        hash_calculado = kdf.derive(senha.encode("utf-8")).hex()
        return hmac.compare_digest(hash_calculado, hash_esperado)
    except (ValueError, IndexError, TypeError):
        return False


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
