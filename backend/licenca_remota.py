"""Cliente da API central de licenças.

O token administrativo existe apenas na configuração do backend do vendedor.
Instalações de clientes usam uma identidade aleatória por conta para consultar
somente a própria licença.
"""
from __future__ import annotations

import base64
import json
import hashlib
import logging
import os
import re
import secrets
from datetime import datetime, timedelta
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

import database
import licenca
import segredos

log = logging.getLogger("adri.licenca_remota")

TIMEOUT_SEGUNDOS = 90
GRACA_OFFLINE_HORAS = 72
API_URL_PADRAO = "https://adri-poltronas-licenses.onrender.com"
CHAVE_INSTALACAO = "ADRI_LICENCA_INSTALLATION_ID"

# -----------------------------------------------------------------------------
# A RESPOSTA DA CENTRAL E ASSINADA
#
# Ate a 1.5.2 o aplicativo acreditava em qualquer JSON que chegasse da URL
# configurada, e depois acreditava no que estivesse gravado nas colunas
# `licenca_remota_*` do SQLite. Duas portas, ambas sem esforco:
#
#   * `ADRI_LICENCA_API_URL` no `.env` do usuario aponta para qualquer
#     servidor -- inclusive `http://localhost` -- que responda `"paid"`;
#   * `UPDATE usuarios SET licenca_remota_estado='paid',
#     licenca_remota_offline_ate='2999-01-01'` libera para sempre.
#
# Agora o servidor assina (Ed25519) o estado, a validade, a conta, a
# instalacao e o instante em que respondeu. O aplicativo confere a assinatura
# com a chave PUBLICA abaixo e le o estado de dentro da prova -- na resposta e
# no cache. Um servidor falso nao tem a chave privada; um cache editado nao
# confere; uma prova copiada de outro computador nao bate com esta instalacao;
# uma prova antiga esta fora da janela de 72 horas contadas da emissao.
#
# A CHAVE VAZIA DESLIGA A EXIGENCIA, e isso e deliberado: exigir assinatura
# antes de o servico publicado assinar trancaria todos os clientes do lado de
# fora. A ativacao e uma ordem de passos, descrita em
# `licensing-service/README.md`: gerar o par, configurar a privada no
# servico, colar a publica aqui, publicar a versao.
#
# E CONSTANTE DE CODIGO, e nao variavel de ambiente, de proposito: lida do
# `.env`, quem redireciona a URL trocaria a chave no mesmo arquivo.
#
# O que isto NAO fecha: atrasar o relogio do Windows continua esticando a
# janela offline, e quem altera o executavel altera tambem esta constante.
# -----------------------------------------------------------------------------
CHAVE_PUBLICA_DA_CENTRAL = ""

PREFIXO_DA_ASSINATURA = b"adri-licenca-v1."
VERSAO_DA_PROVA = 1
TAMANHO_MAXIMO_DA_PROVA = 4096
ESTADOS_DA_CENTRAL = frozenset({"trial", "paid", "suspended", "expired"})
# Estados que liberam o uso. So valem quando vem de dentro de uma prova
# assinada; texto solto no cache serve apenas para lembrar uma recusa.
ESTADOS_QUE_LIBERAM = frozenset({"trial", "paid"})


class LicencaRemotaNegada(RuntimeError):
    """A central recusou uma identidade ou credencial de licença."""


class EndpointRemotoAusente(RuntimeError):
    """Compatibilidade temporária com uma implantação central anterior."""


def _url_base() -> str:
    return (os.environ.get("ADRI_LICENCA_API_URL") or API_URL_PADRAO).strip().rstrip("/")


def _configurada() -> bool:
    return bool(_url_base())


def api_configurada() -> bool:
    return _configurada()


def _url_segura(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme == "https" or parsed.hostname in {"localhost", "127.0.0.1", "::1"}


def _requisicao(
    caminho: str,
    dados: dict | None = None,
    admin: bool = False,
    metodo: str | None = None,
    token_admin: str | None = None,
):
    # O token administrativo nunca é enviado a um host vindo do .env. A URL
    # pública do serviço é fixada no código; sincronizações comuns continuam
    # podendo usar a URL configurada para clientes.
    base = API_URL_PADRAO if admin else _url_base()
    if not base or not _url_segura(base):
        raise RuntimeError("A URL da API central deve usar HTTPS.")
    corpo = json.dumps(dados or {}).encode("utf-8") if dados is not None else None
    cabecalhos = {"Accept": "application/json"}
    if corpo is not None:
        cabecalhos["Content-Type"] = "application/json"
    if admin:
        token = (token_admin if token_admin is not None else
                 segredos.obter("ADRI_LICENCA_ADMIN_TOKEN")).strip()
        if len(token) < 40:
            raise RuntimeError("Token administrativo da API central não configurado.")
        cabecalhos["Authorization"] = "Bearer " + token
    req = Request(base + caminho, data=corpo, headers=cabecalhos,  # noqa: S310
                  method=metodo or ("POST" if corpo is not None else "GET"))
    try:
        # _url_segura rejeita qualquer esquema que não seja HTTPS/loopback.
        with urlopen(req, timeout=TIMEOUT_SEGUNDOS) as resposta:  # noqa: S310
            if resposta.status != 200:
                raise RuntimeError("A API central recusou a solicitação.")
            return json.loads(resposta.read(1024 * 1024).decode("utf-8"))
    except HTTPError as erro:
        if erro.code in (401, 403):
            raise LicencaRemotaNegada("A central recusou esta licença.") from erro
        if erro.code == 404:
            raise EndpointRemotoAusente("O endpoint não existe nesta versão da API central.") from erro
        mensagem = f"A API central recusou a solicitação (HTTP {erro.code})."
        try:
            dados_erro = json.loads(erro.read(64 * 1024).decode("utf-8"))
            if isinstance(dados_erro, dict) and dados_erro.get("erro"):
                mensagem = str(dados_erro["erro"])
        except Exception:  # noqa: BLE001, S110 - o corpo do erro e um extra: se nao der para ler, a mensagem generica acima e o suficiente
            log.debug("Corpo do erro da API central veio ilegivel; usando mensagem generica.")
        raise RuntimeError(mensagem) from erro


def _data_iso(valor: str | None) -> datetime | None:
    if not valor:
        return None
    try:
        data = datetime.fromisoformat(valor.replace("Z", "+00:00"))
        if data.tzinfo:
            return data.astimezone().replace(tzinfo=None)
        return data
    except (ValueError, TypeError):
        return None


def _normalizar(resposta: dict) -> dict:
    agora = datetime.now().replace(microsecond=0)
    expiracao = _data_iso(resposta.get("expira_em"))
    dias = max((expiracao.date() - agora.date()).days, 0) if expiracao else None
    estado_api = resposta.get("estado")
    if estado_api == "paid":
        estado = "paga"
    elif estado_api == "trial" and dias and dias > 0:
        estado = "teste"
    else:
        estado = "expirada"
    return {
        "estado": estado,
        "dias_restantes": dias,
        "expira_em": expiracao.strftime("%Y-%m-%dT%H:%M:%S") if expiracao else "",
        "teste_modo": "central",
        "origem": "central",
        "estado_central": estado_api,
        "valor_centavos": licenca.VALOR_DA_LICENCA_CENTAVOS,
    }


def assinatura_exigida() -> bool:
    """A chave publica da central esta configurada nesta versao?"""
    return bool(CHAVE_PUBLICA_DA_CENTRAL.strip())


def _b64url(texto: str) -> bytes:
    return base64.urlsafe_b64decode(texto.encode("ascii") + b"=" * (-len(texto) % 4))


def verificar_prova(prova, license_id: str, instalacao_id: str) -> dict | None:
    """
    O conteudo da prova, se a assinatura confere e ela e DESTA conta nesta
    instalacao. None em qualquer outro caso -- sem distinguir o motivo para
    quem chama, porque todos pedem a mesma reacao: nao confiar.

    Formato: `<json em base64url>.<assinatura em base64url>`. A assinatura
    cobre os bytes do proprio base64, e nao o JSON reserializado: assim nao ha
    forma canonica para divergir entre as duas pontas.
    """
    if not assinatura_exigida():
        return None
    if not isinstance(prova, str) or not 0 < len(prova) <= TAMANHO_MAXIMO_DA_PROVA:
        return None
    corpo_b64, separador, assinatura_b64 = prova.partition(".")
    if not separador or not corpo_b64 or not assinatura_b64 or "." in assinatura_b64:
        return None

    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

        chave = Ed25519PublicKey.from_public_bytes(
            base64.b64decode(CHAVE_PUBLICA_DA_CENTRAL.strip()))
        chave.verify(_b64url(assinatura_b64),
                     PREFIXO_DA_ASSINATURA + corpo_b64.encode("ascii"))
        dados = json.loads(_b64url(corpo_b64).decode("utf-8"))
    except Exception:  # noqa: BLE001 - assinatura invalida, base64 ruim, chave mal colada: tudo e "nao confere"
        return None

    if not isinstance(dados, dict) or dados.get("v") != VERSAO_DA_PROVA:
        return None
    # Presa a conta e ao computador: uma prova "paga" copiada do banco de
    # outra instalacao nao serve aqui.
    if not license_id or dados.get("license_id") != license_id:
        return None
    if not instalacao_id or dados.get("installation_id") != instalacao_id:
        return None
    if dados.get("estado") not in ESTADOS_DA_CENTRAL:
        return None
    if _data_iso(dados.get("emitida_em")) is None:
        return None
    return dados


def identidade_instalacao() -> str:
    """Identificador estável do Windows, para impedir reset ao apagar o SQLite."""
    if os.name == "nt":
        try:
            import winreg

            acesso = winreg.KEY_READ | getattr(winreg, "KEY_WOW64_64KEY", 0)
            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Microsoft\Cryptography",
                0,
                acesso,
            ) as chave:
                machine_guid, _ = winreg.QueryValueEx(chave, "MachineGuid")
            if isinstance(machine_guid, str) and machine_guid.strip():
                material = "adri-poltronas-installation-v1:" + machine_guid.strip().casefold()
                return hashlib.sha256(material.encode("utf-8")).hexdigest()
        except (OSError, ImportError, ValueError):
            log.warning("[LICENCA] MachineGuid indisponível; usando vínculo DPAPI alternativo.")

    # Fallback para execução de desenvolvimento fora do Windows.
    atual = segredos.obter_do_cofre(CHAVE_INSTALACAO).strip()
    if re.fullmatch(r"[0-9a-f]{64}", atual):
        return atual

    novo = secrets.token_hex(32)
    if not segredos.gravar({CHAVE_INSTALACAO: novo}):
        return ""
    confirmado = segredos.obter_do_cofre(CHAVE_INSTALACAO).strip()
    return confirmado if confirmado == novo else ""


def sincronizar_usuario(user_id: int) -> dict | None:
    """Sincroniza a licença de um usuário autenticado e grava cache local."""
    if not _configurada():
        return None
    conta = database.obter_identidade_licenca_remota(user_id)
    if not conta:
        database.invalidar_licenca_remota_cache(user_id)
        return None
    instalacao_id = identidade_instalacao()
    if not instalacao_id:
        log.error("[LICENCA] Não foi possível persistir o identificador DPAPI desta instalação.")
        return None
    payload = {
        "license_id": conta["licenca_remota_id"],
        "client_secret": conta["licenca_remota_segredo"],
        "installation_id": instalacao_id,
        "username": conta["username"],
        "email": conta.get("email") or "",
    }
    try:
        resposta = _requisicao("/v1/licenses/sync", payload)
    except LicencaRemotaNegada:
        database.invalidar_licenca_remota_cache(user_id)
        log.warning("[LICENCA] A central recusou o vínculo da conta com esta instalação.")
        return None
    except (HTTPError, URLError, TimeoutError, OSError, ValueError, RuntimeError):
        return None
    if not isinstance(resposta, dict):
        return None

    prova = resposta.get("prova") if isinstance(resposta.get("prova"), str) else ""
    agora = datetime.now().replace(microsecond=0)
    offline_ate = agora + timedelta(hours=GRACA_OFFLINE_HORAS)
    if assinatura_exigida():
        dados = verificar_prova(prova, conta["licenca_remota_id"], instalacao_id)
        if dados is None:
            # Nao e uma recusa da central: e uma resposta que nao veio dela
            # (ou veio de uma versao que ainda nao assina). O cache fica como
            # esta -- continua valendo ate a janela dele acabar, e nada do
            # que chegou agora e gravado.
            log.error("[LICENCA] Resposta da API central sem assinatura valida; ignorada.")
            return None
        # O que vale e o que esta ASSINADO. Os campos soltos da resposta
        # poderiam dizer outra coisa.
        resposta = {**resposta, "estado": dados["estado"],
                    "expira_em": dados.get("expira_em") or ""}
        # A janela offline conta do instante em que o SERVIDOR respondeu.
        offline_ate = _data_iso(dados["emitida_em"]) + timedelta(hours=GRACA_OFFLINE_HORAS)

    normalizada = _normalizar(resposta)
    normalizada["verificada_em"] = agora.strftime("%Y-%m-%dT%H:%M:%S")
    normalizada["offline_ate"] = offline_ate.strftime("%Y-%m-%dT%H:%M:%S")
    database.gravar_licenca_remota(user_id, normalizada, prova=prova)
    return normalizada


def _ler_cache(user_id: int) -> tuple[str, str, datetime | None]:
    """
    (estado da central, validade, fim da janela offline) que o cache sustenta.

    Estado vazio significa "nao ha nada em que confiar": e preciso falar com a
    central.

    Com a assinatura exigida, estado e validade saem de DENTRO da prova, e a
    janela conta da emissao assinada -- as colunas de texto nao concedem nada.
    Elas continuam valendo para uma coisa so: lembrar, por um minuto, que a
    central acabou de recusar esta conta, para nao repetir a consulta a cada
    requisicao. Adulterar o cache nessa direcao so bloqueia quem adulterou.
    """
    cache = database.obter_licenca_remota_cache(user_id)
    if not cache:
        return "", "", None

    if not assinatura_exigida():
        return (cache.get("estado") or "", cache.get("expira_em") or "",
                _data_iso(cache.get("offline_ate")))

    dados = verificar_prova(cache.get("prova"), cache.get("license_id") or "",
                            identidade_instalacao())
    if dados is not None:
        return (dados["estado"], dados.get("expira_em") or "",
                _data_iso(dados["emitida_em"]) + timedelta(hours=GRACA_OFFLINE_HORAS))

    estado = cache.get("estado") or ""
    if estado in ESTADOS_QUE_LIBERAM:
        return "", "", None
    return estado, "", _data_iso(cache.get("offline_ate"))


def situacao_em_cache(user_id: int) -> dict | None:
    """Retorna cache por até 72 horas; depois exige contato com o servidor."""
    estado_api, expira_em, offline_ate = _ler_cache(user_id)
    if not estado_api:
        return None
    agora = datetime.now().replace(microsecond=0)
    if not offline_ate or agora > offline_ate:
        return {
            "estado": "expirada",
            "dias_restantes": 0,
            "origem": "central",
            "valor_centavos": licenca.VALOR_DA_LICENCA_CENTAVOS,
        }
    if estado_api == "paid":
        estado, dias = "paga", None
    elif estado_api == "trial":
        expira = _data_iso(expira_em)
        dias = max((expira.date() - agora.date()).days, 0) if expira else 0
        estado = "teste" if dias > 0 else "expirada"
    else:
        estado, dias = "expirada", 0
    return {
        "estado": estado,
        "dias_restantes": dias,
        "expira_em": expira_em,
        "origem": "central",
        "teste_modo": "central",
        "valor_centavos": licenca.VALOR_DA_LICENCA_CENTAVOS,
    }


def cache_precisa_sincronizar(user_id: int) -> bool:
    """True quando ainda não há resposta central válida para uso offline."""
    estado_api, _expira_em, offline_ate = _ler_cache(user_id)
    if not estado_api:
        return True
    agora = datetime.now().replace(microsecond=0)
    return not offline_ate or agora > offline_ate


def listar_contas_admin() -> dict:
    return _requisicao("/v1/admin/licenses", admin=True)


def validar_token_admin(token: str) -> bool:
    """Valida a chave de ativação diretamente com o serviço central fixado."""
    if not isinstance(token, str) or len(token.strip()) < 40:
        return False
    try:
        resposta = _requisicao(
            "/v1/admin/verify", admin=True, token_admin=token.strip()
        )
        return resposta.get("valid") is True
    except EndpointRemotoAusente:
        # A versão publicada anteriormente não tinha o endpoint leve. Usa a
        # listagem existente até que o serviço central seja atualizado.
        try:
            resposta = _requisicao(
                "/v1/admin/licenses", admin=True, token_admin=token.strip()
            )
            return isinstance(resposta.get("contas"), list)
        except (HTTPError, URLError, TimeoutError, OSError, ValueError, RuntimeError):
            return False
    except (HTTPError, URLError, TimeoutError, OSError, ValueError, RuntimeError):
        return False


def controlar_conta_admin(license_id: str, acao: str) -> dict:
    if acao not in {"paid", "trial_30_days", "suspend"}:
        raise ValueError("Ação de licença inválida.")
    if not license_id or len(license_id) > 64 or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-" for c in license_id):
        raise ValueError("Identificador de licença inválido.")
    return _requisicao("/v1/admin/licenses/" + license_id, {"acao": acao}, admin=True, metodo="POST")
