"""Cliente da API central de licenças.

O token administrativo existe apenas na configuração do backend do vendedor.
Instalações de clientes usam uma identidade aleatória por conta para consultar
somente a própria licença.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

import database
import licenca
import segredos

TIMEOUT_SEGUNDOS = 10
GRACA_OFFLINE_HORAS = 72


def _url_base() -> str:
    return (os.environ.get("ADRI_LICENCA_API_URL") or "").strip().rstrip("/")


def _configurada() -> bool:
    return bool(_url_base())


def api_configurada() -> bool:
    return _configurada()


def _url_segura(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme == "https" or parsed.hostname in {"localhost", "127.0.0.1", "::1"}


def _requisicao(caminho: str, dados: dict | None = None, admin: bool = False, metodo: str | None = None):
    base = _url_base()
    if not base or not _url_segura(base):
        raise RuntimeError("A URL da API central deve usar HTTPS.")
    corpo = json.dumps(dados or {}).encode("utf-8") if dados is not None else None
    cabecalhos = {"Accept": "application/json"}
    if corpo is not None:
        cabecalhos["Content-Type"] = "application/json"
    if admin:
        token = segredos.obter("ADRI_LICENCA_ADMIN_TOKEN").strip()
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
            return json.loads(resposta.read(64 * 1024).decode("utf-8"))
    except HTTPError as erro:
        mensagem = f"A API central recusou a solicitação (HTTP {erro.code})."
        try:
            dados_erro = json.loads(erro.read(64 * 1024).decode("utf-8"))
            if isinstance(dados_erro, dict) and dados_erro.get("erro"):
                mensagem = str(dados_erro["erro"])
        except Exception:
            pass
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


def sincronizar_usuario(user_id: int) -> dict | None:
    """Sincroniza a licença de um usuário autenticado e grava cache local."""
    if not _configurada():
        return None
    conta = database.obter_identidade_licenca_remota(user_id)
    if not conta:
        return None
    payload = {
        "license_id": conta["licenca_remota_id"],
        "client_secret": conta["licenca_remota_segredo"],
        "username": conta["username"],
        "email": conta.get("email") or "",
    }
    try:
        resposta = _requisicao("/v1/licenses/sync", payload)
    except (HTTPError, URLError, TimeoutError, OSError, ValueError, RuntimeError):
        return None
    normalizada = _normalizar(resposta)
    agora = datetime.now().replace(microsecond=0)
    normalizada["verificada_em"] = agora.strftime("%Y-%m-%dT%H:%M:%S")
    normalizada["offline_ate"] = (agora + timedelta(hours=GRACA_OFFLINE_HORAS)).strftime("%Y-%m-%dT%H:%M:%S")
    database.gravar_licenca_remota(user_id, normalizada)
    return normalizada


def situacao_em_cache(user_id: int) -> dict | None:
    """Retorna cache por até 72 horas; depois exige contato com o servidor."""
    cache = database.obter_licenca_remota_cache(user_id)
    if not cache or not cache.get("estado"):
        return None
    agora = datetime.now().replace(microsecond=0)
    offline_ate = _data_iso(cache.get("offline_ate"))
    if not offline_ate or agora > offline_ate:
        return {
            "estado": "expirada",
            "dias_restantes": 0,
            "origem": "central",
            "valor_centavos": licenca.VALOR_DA_LICENCA_CENTAVOS,
        }
    estado_api = cache.get("estado")
    if estado_api == "paid":
        estado, dias = "paga", None
    elif estado_api == "trial":
        expira = _data_iso(cache.get("expira_em"))
        dias = max((expira.date() - agora.date()).days, 0) if expira else 0
        estado = "teste" if dias > 0 else "expirada"
    else:
        estado, dias = "expirada", 0
    return {
        "estado": estado,
        "dias_restantes": dias,
        "expira_em": cache.get("expira_em", ""),
        "origem": "central",
        "teste_modo": "central",
        "valor_centavos": licenca.VALOR_DA_LICENCA_CENTAVOS,
    }


def listar_contas_admin() -> dict:
    return _requisicao("/v1/admin/licenses", admin=True)


def controlar_conta_admin(license_id: str, acao: str) -> dict:
    if acao not in {"paid", "trial_30_days", "suspend"}:
        raise ValueError("Ação de licença inválida.")
    if not license_id or len(license_id) > 64 or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-" for c in license_id):
        raise ValueError("Identificador de licença inválido.")
    return _requisicao("/v1/admin/licenses/" + license_id, {"acao": acao}, admin=True, metodo="POST")
