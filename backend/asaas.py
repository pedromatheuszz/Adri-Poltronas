"""
Módulo de integração com a API Asaas (v3).

Suporta:
  - Criação de clientes no Asaas
  - Geração de cobranças via Pix (QR Code + Copia e Cola)
  - Geração de cobranças via Boleto
  - Consulta de status de pagamento
  - Cancelamento de cobranças

Variáveis de ambiente:
  ASAAS_API_KEY    – Chave de acesso à API Asaas (obrigatória)
  ASAAS_SANDBOX    – 'true' para ambiente sandbox (opcional, padrão: true)
"""
import json
import logging
import os
import sys
import urllib.request
import urllib.error
import urllib.parse

_log = logging.getLogger("adri.asaas")
_APP_NAME = "AdriPoltronas/1.0"

# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------
_API_KEY = os.environ.get("ASAAS_API_KEY", "")
_SANDBOX = os.environ.get("ASAAS_SANDBOX", "true").lower() == "true"

_BASE_URL_SANDBOX = "https://api-sandbox.asaas.com/v3"
_BASE_URL_PROD = "https://api.asaas.com/v3"


def _base_url() -> str:
    return _BASE_URL_SANDBOX if _SANDBOX else _BASE_URL_PROD


def _headers(content_type=True):
    h = {
        "access_token": _API_KEY,
        "User-Agent": _APP_NAME,
    }
    if content_type:
        h["Content-Type"] = "application/json"
    return h


def _request(method, path, body=None):
    """Executa uma requisição HTTP à API Asaas e retorna o dict JSON."""
    url = _base_url() + path
    data = json.dumps(body).encode("utf-8") if body else None
    req = urllib.request.Request(url, data=data, headers=_headers(), method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        corpo = e.read().decode("utf-8", errors="replace")
        _log.error("Asaas %s %s → %s: %s", method, path, e.code, corpo)
        try:
            return {"_erro": True, "_status": e.code, **json.loads(corpo)}
        except Exception:
            return {"_erro": True, "_status": e.code, "_detalhe": corpo}
    except Exception as e:
        _log.exception("Asaas conexao falhou: %s", e)
        return {"_erro": True, "_detalhe": str(e)}


def _request_get(path):
    """Requisição GET (sem body)."""
    url = _base_url() + path
    req = urllib.request.Request(url, headers=_headers(content_type=False), method="GET")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        corpo = e.read().decode("utf-8", errors="replace")
        _log.error("Asaas GET %s → %s: %s", path, e.code, corpo)
        try:
            return {"_erro": True, "_status": e.code, **json.loads(corpo)}
        except Exception:
            return {"_erro": True, "_status": e.code, "_detalhe": corpo}
    except Exception as e:
        _log.exception("Asaas GET conexao falhou: %s", e)
        return {"_erro": True, "_detalhe": str(e)}


def _request_delete(path):
    """Requisição DELETE."""
    url = _base_url() + path
    req = urllib.request.Request(url, headers=_headers(content_type=False), method="DELETE")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        corpo = e.read().decode("utf-8", errors="replace")
        _log.error("Asaas DELETE %s → %s: %s", path, e.code, corpo)
        try:
            return {"_erro": True, "_status": e.code, **json.loads(corpo)}
        except Exception:
            return {"_erro": True, "_status": e.code, "_detalhe": corpo}
    except Exception as e:
        _log.exception("Asaas DELETE conexao falhou: %s", e)
        return {"_erro": True, "_detalhe": str(e)}


def esta_configurado():
    """Retorna True se a chave de API está configurada."""
    return bool(_API_KEY)


def ambiente():
    """Retorna 'sandbox' ou 'producao'."""
    return "sandbox" if _SANDBOX else "producao"


# ---------------------------------------------------------------------------
# Clientes
# ---------------------------------------------------------------------------
def criar_cliente(nome, cpf_cnpj=None, email=None, telefone=None, cidade=None, uf=None, bairro=None, rua=None, cep=None):
    """
    Cria um cliente no Asaas. Retorna dict com 'id' do cliente Asaas ou '_erro'.
    cpf_cnpj é obrigatório pela API, mas pode ser None (Asaas aceita sem doc).
    """
    body = {"name": nome}
    if cpf_cnpj:
        # Remove caracteres não numéricos
        body["cpfCnpj"] = "".join(c for c in str(cpf_cnpj) if c.isdigit())
    if email:
        body["email"] = email
    if telefone:
        body["mobilePhone"] = "".join(c for c in str(telefone) if c.isdigit())
    if cidade:
        body["city"] = cidade
    if uf:
        body["state"] = uf
    if bairro:
        body["neighborhood"] = bairro
    if rua:
        body["address"] = rua
    if cep:
        body["zipCode"] = "".join(c for c in str(cep) if c.isdigit())

    resultado = _request("POST", "/customers", body)
    if resultado.get("_erro"):
        return resultado
    return {"id": resultado.get("id"), "nome": resultado.get("name")}


def obter_cliente(asaas_customer_id):
    """Retorna dados de um cliente Asaas pelo ID."""
    return _request_get(f"/customers/{asaas_customer_id}")


# ---------------------------------------------------------------------------
# Cobranças – PIX
# ---------------------------------------------------------------------------
def criar_cobranca_pix(asaas_customer_id, valor, data_vencimento, descricao=""):
    """
    Cria uma cobrança Pix no Asaas.
    valor: float (ex: 150.00)
    data_vencimento: str 'YYYY-MM-DD'
    Retorna dict com dados da cobrança ou '_erro'.
    """
    body = {
        "customer": asaas_customer_id,
        "billingType": "PIX",
        "value": round(float(valor), 2),
        "dueDate": data_vencimento,
    }
    if descricao:
        body["description"] = descricao
    return _request("POST", "/payments", body)


def obter_qr_code_pix(asaas_payment_id):
    """
    Obtém o QR Code e o payload 'Copia e Cola' de uma cobrança Pix.
    Retorna dict com 'encodedImage' (base64) e 'payload' (pix copia e cola).
    """
    return _request_get(f"/payments/{asaas_payment_id}/pixQrCode")


# ---------------------------------------------------------------------------
# Cobranças – BOLETO
# ---------------------------------------------------------------------------
def criar_cobranca_boleto(asaas_customer_id, valor, data_vencimento, descricao=""):
    """
    Cria uma cobrança Boleto no Asaas.
    Retorna dict com dados da cobrança (inclui 'bankSlipUrl').
    """
    body = {
        "customer": asaas_customer_id,
        "billingType": "BOLETO",
        "value": round(float(valor), 2),
        "dueDate": data_vencimento,
        "postalService": False,
    }
    if descricao:
        body["description"] = descricao
    return _request("POST", "/payments", body)


# ---------------------------------------------------------------------------
# Consulta e Cancelamento
# ---------------------------------------------------------------------------
def obter_pagamento(asaas_payment_id):
    """Retorna dados completos de uma cobrança pelo ID."""
    return _request_get(f"/payments/{asaas_payment_id}")


def obter_status_pagamento(asaas_payment_id):
    """Retorna apenas o status de uma cobrança."""
    return _request_get(f"/payments/{asaas_payment_id}/status")


def cancelar_pagamento(asaas_payment_id):
    """Cancela uma cobrança pendente (não paga)."""
    return _request_delete(f"/payments/{asaas_payment_id}")
