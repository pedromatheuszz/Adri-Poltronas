"""
Módulo de segurança: criptografia de segredos em repouso.

Em Windows, usa DPAPI (Data Protection API) através de `win32crypt` —
proteção ligada à conta de usuário do SO. Nenhuma chave precisa ser
armazenada: o Windows deriva a chave do logon do usuário.

Em outras plataformas (apenas para dev fora do app empacotado), usa
base64 + flag de marcação para deixar claro que NÃO está cifrado.
Em produção (PyInstaller), o fallback PLAIN é recusado por segurança.
"""
import base64
import os
import sys

# Tenta importar DPAPI (só disponível em Windows)
# A função _importar_win32crypt() faz a tentativa sob demanda.

try:
    import win32crypt  # type: ignore
except ImportError:
    pass


PREFIXO_DPAPI = "DPAPI1:"  # Marcador para identificar valor cifrado por DPAPI
PREFIXO_PLAIN = "PLAIN1:"  # Marcador para identificar valor em texto puro (legado)

# Em produção (PyInstaller) o fallback PLAIN é proibido para não expor tokens.
# Detecção: PyInstaller define sys.frozen=True quando o app está empacotado.
PRODUCAO = bool(getattr(sys, 'frozen', False))


def _importar_win32crypt():
    """Importa win32crypt sob demanda; retorna o módulo ou None."""
    if not sys.platform.startswith("win"):
        return None
    try:
        import win32crypt  # type: ignore
        return win32crypt
    except ImportError:
        return None


def cifrar(texto: str) -> str:
    """
    Cifra uma string. Em Windows usa DPAPI; fora dele apenas marca o valor.
    Retorna string com prefixo indicando o esquema.

    Em produção, se DPAPI não estiver disponível, levanta RuntimeError
    em vez de cair no fallback PLAIN (que seria um vazamento de segredo).
    """
    if texto is None:
        return ""
    if not isinstance(texto, str):
        texto = str(texto)

    wc = _importar_win32crypt()
    if wc is not None:
        dados = texto.encode("utf-8")
        # pywin32 expõe CryptProtectData (não ProtectData) para cifrar via DPAPI.
        # flags=0 = escopo usuário atual (chave derivada do logon do Windows).
        cifrado = wc.CryptProtectData(dados, None, None, None, None, 0)
        return PREFIXO_DPAPI + base64.b64encode(cifrado).decode("ascii")

    if PRODUCAO:
        # Segurança: em produção, NÃO aceitamos fallback em texto claro.
        raise RuntimeError(
            "DPAPI indisponível em ambiente de produção. "
            "Cifragem de segredos abortada para não expor o token."
        )

    # Fallback dev: não está cifrado de fato, mas mantém o prefixo claro.
    # Warning explícito para deixar visível em logs.
    print(
        "[security][AVISO] Cifrando em modo PLAINTEXT (apenas dev). "
        "Não use em produção.",
        file=sys.stderr,
    )
    return PREFIXO_PLAIN + base64.b64encode(texto.encode("utf-8")).decode("ascii")


def decifrar(valor: str):
    """
    Decifra um valor previamente cifrado por `cifrar()`.
    Aceita também valores legados em texto puro (sem prefixo).
    Retorna a string original ou None se o valor estiver vazio.

    Em produção, valores marcados como PLAIN1 (legado dev) são RECUSADOS
    para impedir que um banco gerado em dev seja lido em prod.
    """
    if not valor:
        return None

    if valor.startswith(PREFIXO_DPAPI):
        wc = _importar_win32crypt()
        if wc is None:
            return None
        bruto = base64.b64decode(valor[len(PREFIXO_DPAPI):])
        try:
            # pywin32: CryptUnprotectData retorna (descricao, dados_decifrados).
            resultado = wc.CryptUnprotectData(bruto, None, None, None, 0)
            return resultado[1].decode("utf-8")
        except Exception:
            return None

    if valor.startswith(PREFIXO_PLAIN):
        if PRODUCAO:
            # Segurança: dados legados em plaintext não devem rodar em prod.
            print(
                "[security][ALERTA] Valor PLAINTEXT encontrado em produção. "
                "Recusando decifrar para evitar exposição. "
                "Re-cifre o banco com `migrar_para_cifrado()` em dev e reimporte.",
                file=sys.stderr,
            )
            return None
        try:
            return base64.b64decode(valor[len(PREFIXO_PLAIN):]).decode("utf-8")
        except Exception:
            return None

    # Valor legado: texto puro, sem prefixo. Em prod, recusamos.
    if PRODUCAO:
        print(
            "[security][ALERTA] Valor sem prefixo de cifragem em produção. "
            "Recusando para evitar exposição de segredo em texto claro.",
            file=sys.stderr,
        )
        return None
    return valor


def migrar_para_cifrado(valor: str) -> str:
    """
    Recebe um valor que pode estar em texto puro (legado) e retorna
    sua versão cifrada. Idempotente: se já estiver cifrado, retorna igual.
    """
    if not valor:
        return valor
    if valor.startswith((PREFIXO_DPAPI, PREFIXO_PLAIN)):
        # Já está marcado; re-cifra apenas se for PLAIN legado
        if valor.startswith(PREFIXO_PLAIN):
            claro = decifrar(valor) or ""
            return cifrar(claro)
        return valor
    # Texto puro sem prefixo: cifra agora
    return cifrar(valor)
