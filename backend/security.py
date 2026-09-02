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
import hashlib
import re
import secrets
import json
import time
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
# CSRF Token
# ---------------------------------------------------------------------------

_csrf_store: dict = {}
_csrf_expiry_seconds = 3600


def gerar_csrf_token(usuario_id: str = "default") -> str:
    """Gera um token CSRF unico com timestamp de expiracao."""
    token = secrets.token_urlsafe(32)
    _csrf_store[token] = {
        "usuario_id": usuario_id,
        "criado_em": time.time(),
        "usado": False,
    }
    _limpar_csrf_expirados()
    return token


def validar_csrf_token(token: str, usuario_id: str = "default") -> bool:
    """Valida um token CSRF. Retorna True se valido e nao expirado."""
    _limpar_csrf_expirados()
    if token not in _csrf_store:
        log.warning("[CSRF] Token nao encontrado.")
        return False
    dado = _csrf_store[token]
    if dado["usado"]:
        log.warning("[CSRF] Token ja utilizado (replay).")
        return False
    if time.time() - dado["criado_em"] > _csrf_expiry_seconds:
        del _csrf_store[token]
        log.warning("[CSRF] Token expirado.")
        return False
    if dado["usuario_id"] != usuario_id:
        log.warning("[CSRF] Token para usuario diferente.")
        return False
    dado["usado"] = True
    return True


def _limpar_csrf_expirados():
    agora = time.time()
    expirados = [k for k, v in _csrf_store.items()
                 if agora - v["criado_em"] > _csrf_expiry_seconds]
    for k in expirados:
        del _csrf_store[k]


# ---------------------------------------------------------------------------
# Gerenciamento de Sessao Segura com Expiracao
# ---------------------------------------------------------------------------

_sessoes: dict = {}
_SESSAO_TIMEOUT = 28800


def criar_sessao_segura(conta: str, token: str) -> str:
    """Cria uma sessao segura com ID unico e timestamp de expiracao."""
    sessao_id = secrets.token_urlsafe(24)
    _sessoes[sessao_id] = {
        "conta": conta,
        "token": token,
        "criado_em": time.time(),
        "ultimo_acesso": time.time(),
        "ip_hash": None,
        "user_agent_hash": None,
    }
    _limpar_sessoes_expiradas()
    return sessao_id


def validar_sessao_segura(sessao_id: str, ip_remoto: str = None, user_agent: str = None) -> Optional[dict]:
    """
    Valida a sessao pelo ID e devolve seus dados, ou None se ela nao existe
    ou ja expirou.

    `ip_remoto` e `user_agent`, quando informados, sao apenas REGISTRADOS
    (em hash) na sessao. Nao ha comparacao com o valor anterior, ou seja,
    nao existe bind de IP/User-Agent aqui.
    """
    _limpar_sessoes_expiradas()
    if sessao_id not in _sessoes:
        return None
    sessao = _sessoes[sessao_id]
    idade = time.time() - sessao["criado_em"]
    if idade > _SESSAO_TIMEOUT:
        del _sessoes[sessao_id]
        return None
    sessao["ultimo_acesso"] = time.time()
    if ip_remoto:
        sessao["ip_hash"] = _hash_ip(ip_remoto)
    if user_agent:
        sessao["user_agent_hash"] = hashlib.sha256(user_agent.encode()).hexdigest()
    return sessao


def destruir_sessao_segura(sessao_id: str):
    """Destroi uma sessao por ID."""
    _sessoes.pop(sessao_id, None)


def _limpar_sessoes_expiradas():
    agora = time.time()
    expiradas = [k for k, v in _sessoes.items()
                 if agora - v["criado_em"] > _SESSAO_TIMEOUT]
    for k in expiradas:
        del _sessoes[k]


def _hash_ip(ip: str) -> str:
    return hashlib.sha256(ip.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Sanitizacao de Input
# ---------------------------------------------------------------------------
_RE_INJECAO_SQL = re.compile(r"(?:'|;|--|\bOR\b|\bAND\b|\bDROP\b|\bDELETE\b|\bINSERT\b|\bUPDATE\b|\bEXEC\b|\bUNION\b|\bSELECT\b)", re.IGNORECASE)
_RE_TAG_SCRIPT = re.compile(r"<script[^>]*>.*?</script>", re.IGNORECASE | re.DOTALL)
_RE_EVENT_HANDLER = re.compile(r"\bon\w+\s*=", re.IGNORECASE)
_RE_JAVASCRIPT_PROTO = re.compile(r"javascript\s*:", re.IGNORECASE)
_RE_DATA_URI = re.compile(r"data\s*:", re.IGNORECASE)


def sanitizar_texto(texto: str, max_len: int = 1000) -> str:
    """Remove tags script, handlers de evento, e proto javascript de um texto."""
    if not isinstance(texto, str):
        return ""
    texto = texto[:max_len]
    texto = _RE_TAG_SCRIPT.sub("", texto)
    texto = _RE_EVENT_HANDLER.sub("", texto)
    texto = _RE_JAVASCRIPT_PROTO.sub("", texto)
    texto = _RE_DATA_URI.sub("", texto)
    texto = texto.strip()
    return texto


def sanitizar_html(texto: str) -> str:
    """Escapa entidades HTML para prevencao de XSS."""
    if not isinstance(texto, str):
        return ""
    return (texto
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&#x27;"))


def validar_sql_safe(consulta: str, params: tuple = ()) -> bool:
    """Verifica se uma consulta SQL parece segura (usando parametros)."""
    if params:
        return True
    if _RE_INJECAO_SQL.search(consulta):
        log.warning("[SQL-INJECTION] Consulta potencialmente insegura detectada.")
        return False
    return True


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


def validar_upload(arquivo, max_size: int = _TAMANHO_MAXIMO_UPLOAD) -> tuple:
    """
    Valida um arquivo uploadado. Retorna (valido: bool, erro: str ou None).
    """
    if arquivo is None:
        return False, "Nenhum arquivo fornecido."

    tamanho = len(arquivo.read()) if hasattr(arquivo, 'read') else 0
    if hasattr(arquivo, 'seek'):
        arquivo.seek(0)

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


# ---------------------------------------------------------------------------
# Deteccao de Forca Bruta
# ---------------------------------------------------------------------------

_brute_force_tentativas: dict = {}
_BRUTE_FORCE_MAX_TENTATIVAS = 5
# Janela deslizante. O bloqueio dura enquanto houver MAX_TENTATIVAS dentro
# dela: passados 5 minutos sem novas tentativas, o IP volta a ser aceito.
_BRUTE_FORCE_JANELA = 300  # 5 minutos


def registrar_tentativa_login(endereco_ip: str, sucesso: bool):
    """Registra uma tentativa de login para deteccao de bruteforce."""
    agora = time.time()
    if endereco_ip not in _brute_force_tentativas:
        _brute_force_tentativas[endereco_ip] = []

    tentativas = _brute_force_tentativas[endereco_ip]
    tentativas.append(agora)

    tentativas = [t for t in tentativas if agora - t < _BRUTE_FORCE_JANELA]
    _brute_force_tentativas[endereco_ip] = tentativas

    if sucesso:
        _brute_force_tentativas.pop(endereco_ip, None)


def esta_bloqueado_bruteforce(endereco_ip: str) -> bool:
    """Verifica se o endereco IP esta bloqueado por bruteforce."""
    agora = time.time()
    if endereco_ip not in _brute_force_tentativas:
        return False
    tentativas = _brute_force_tentativas[endereco_ip]
    recentes = [t for t in tentativas if agora - t < _BRUTE_FORCE_JANELA]
    if len(recentes) >= _BRUTE_FORCE_MAX_TENTATIVAS:
        return True
    return False


# ---------------------------------------------------------------------------
# Assinatura de Requisicoes (Request Signing)
# ---------------------------------------------------------------------------

def assinar_request(dados: dict, segredo: str) -> str:
    """Gera uma assinatura HMAC-SHA256 para dados de requisicao."""
    payload = json.dumps(dados, sort_keys=True, separators=(',', ':'))
    return hmac.new(segredo.encode(), payload.encode(), hashlib.sha256).hexdigest()


def verificar_assinatura(dados: dict, segredo: str, assinatura: str) -> bool:
    """Verifica se a assinatura HMAC corresponde aos dados."""
    esperada = assinar_request(dados, segredo)
    return hmac.compare_digest(esperada, assinatura)


# ---------------------------------------------------------------------------
# Deteccao de Anomalias de Dados
# ---------------------------------------------------------------------------

def detectar_anomalia_cliente(dados: dict, historico_consultas: list = None) -> dict:
    """
    Analisa dados do cliente para detectar anomalias.
    Retorna dict com 'eh_anomalo': bool e 'motivos': list.

    `historico_consultas` e aceito para compatibilidade da assinatura, mas
    nao influencia o resultado: nenhuma regra hoje depende do historico.
    """
    anomalias = {"eh_anomalo": False, "motivos": []}

    nome = str(dados.get('nome', ''))
    if len(nome) > 200:
        anomalias["motivos"].append("Nome excepcionalmente longo")
        anomalias["eh_anomalo"] = True

    cep = str(dados.get('cep', ''))
    cep_limpo = cep.replace('-', '').replace('.', '').replace(' ', '')
    if not cep_limpo.isdigit() or len(cep_limpo) != 8:
        anomalias["motivos"].append("CEP invalido")
        anomalias["eh_anomalo"] = True

    observacoes = str(dados.get('observacoes', ''))
    if len(observacoes) > 5000:
        anomalias["motivos"].append("Observacoes excepcionalmente longas")
        anomalias["eh_anomalo"] = True

    return anomalias