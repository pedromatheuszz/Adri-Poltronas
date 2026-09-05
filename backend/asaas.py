"""
Módulo de integração com a API Asaas (v3).

Suporta:
  - Criação de clientes no Asaas
  - Geração de cobranças via Pix (QR Code + Copia e Cola)
  - Geração de cobranças via Boleto
  - Consulta de status de pagamento
  - Cancelamento de cobranças

Variáveis de ambiente (lidas via `config`, que carrega o .env):
  ASAAS_API_KEY    – Chave de acesso à API Asaas (obrigatória)
  ASAAS_SANDBOX    – 'true' para ambiente sandbox (opcional, padrão: true)
"""
import json
import logging
import urllib.request
import urllib.error
import urllib.parse

import config

_log = logging.getLogger("adri.asaas")
_APP_NAME = "AdriPoltronas/1.0"

# ---------------------------------------------------------------------------
# Configuração
#
# A leitura é feita através de `config` (que executa load_dotenv no import) e
# não por snapshot de os.environ no import deste módulo. Um snapshot aqui seria
# lido antes do .env ser carregado — a cadeia database -> asaas acontece antes
# do load_dotenv de app.py — deixando a chave vazia sem nenhum aviso.
# ---------------------------------------------------------------------------
_BASE_URL_SANDBOX = "https://api-sandbox.asaas.com/v3"
_BASE_URL_PROD = "https://api.asaas.com/v3"


def _api_key() -> str:
    return config.ASAAS_API_KEY


def _base_url() -> str:
    return _BASE_URL_SANDBOX if config.ASAAS_SANDBOX else _BASE_URL_PROD


def _headers(content_type=True):
    h = {
        "access_token": _api_key(),
        "User-Agent": _APP_NAME,
    }
    if content_type:
        h["Content-Type"] = "application/json"
    return h


def _codigos_do_erro(corpo: str) -> list:
    """
    Os codigos de erro do Asaas, sem o resto do corpo.

    O corpo bruto de uma recusa REPETE o que foi enviado. Numa recusa de
    criacao de cliente isso e nome, CPF/CNPJ, e-mail e telefone em texto claro
    -- e o `app.log` fica em %APPDATA% sem cifragem, rodando por 5 arquivos de
    2 MB. Destoava do resto do projeto, onde os tokens da Microsoft e as
    chaves de integracao sao cifrados via DPAPI, e contrariava o PRIVACIDADE.md.

    Os codigos ("invalid_cpfCnpj", "invalid_value") identificam a causa sem
    repetir o cadastro, que e para o que o log serve.
    """
    try:
        detalhe = json.loads(corpo)
    except (ValueError, TypeError):
        return []
    if not isinstance(detalhe, dict):
        return []
    erros = detalhe.get("errors")
    if not isinstance(erros, list):
        return []
    return [erro.get("code", "") for erro in erros if isinstance(erro, dict)]


def _diagnostico(corpo: str) -> str:
    """O que vai para o log quando o Asaas recusa. Nunca o corpo."""
    codigos = [c for c in _codigos_do_erro(corpo) if c]
    if codigos:
        return ", ".join(codigos)
    # Sem codigos nao ha o que citar sem arriscar dado pessoal. O tamanho ao
    # menos separa "respondeu vazio" de "respondeu algo que nao entendemos".
    return f"<sem codigo; {len(corpo)} bytes no corpo>"


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
        _log.error("Asaas %s %s → %s: %s", method, path, e.code, _diagnostico(corpo))
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
        _log.error("Asaas GET %s → %s: %s", path, e.code, _diagnostico(corpo))
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
        _log.error("Asaas DELETE %s → %s: %s", path, e.code, _diagnostico(corpo))
        try:
            return {"_erro": True, "_status": e.code, **json.loads(corpo)}
        except Exception:
            return {"_erro": True, "_status": e.code, "_detalhe": corpo}
    except Exception as e:
        _log.exception("Asaas DELETE conexao falhou: %s", e)
        return {"_erro": True, "_detalhe": str(e)}


def esta_configurado():
    """Retorna True se a chave de API está configurada."""
    return bool(_api_key())


def ambiente():
    """Retorna 'sandbox' ou 'producao'."""
    return "sandbox" if config.ASAAS_SANDBOX else "producao"


def chave_incompativel_com_ambiente() -> bool:
    """
    True quando o prefixo da chave não bate com o ambiente selecionado.
    Uma chave $aact_prod_* apontando para o sandbox (ou vice-versa) sempre
    resulta em 401 — vale detectar isso no boot em vez de na primeira cobrança.
    """
    chave = _api_key()
    if not chave:
        return False
    if config.ASAAS_SANDBOX:
        return '_prod_' in chave
    return '_hmlg_' in chave


# ---------------------------------------------------------------------------
# Clientes
# ---------------------------------------------------------------------------
def criar_cliente(nome, cpf_cnpj=None, email=None, telefone=None, cidade=None, uf=None, bairro=None, rua=None, cep=None):
    """
    Cria um cliente no Asaas. Retorna dict com 'id' do cliente Asaas ou '_erro'.
    cpf_cnpj pode ser None: a API Asaas aceita cadastro sem documento.
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
def criar_cobranca_pix(asaas_customer_id, valor, data_vencimento, descricao="",
                       referencia_externa=""):
    """
    Cria uma cobrança Pix no Asaas.
    valor: float (ex: 150.00)
    data_vencimento: str 'YYYY-MM-DD'
    referencia_externa: identificador nosso, para reconciliar depois de uma
        chamada cujo resultado se perdeu. Ver `emissao.py`.
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
    if referencia_externa:
        body["externalReference"] = referencia_externa
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
def criar_cobranca_boleto(asaas_customer_id, valor, data_vencimento, descricao="",
                          referencia_externa=""):
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
    if referencia_externa:
        body["externalReference"] = referencia_externa
    return _request("POST", "/payments", body)


# ---------------------------------------------------------------------------
# Consulta e Cancelamento
# ---------------------------------------------------------------------------
def obter_pagamento(asaas_payment_id):
    """Retorna dados completos de uma cobrança pelo ID."""
    return _request_get(f"/payments/{asaas_payment_id}")


def buscar_por_referencia_externa(referencia_externa):
    """
    Procura a cobrança que carrega esta referência nossa.

    É o que torna a emissão recuperável. Criar uma cobrança é uma chamada de
    rede: o Asaas pode ter processado e a resposta ter se perdido no caminho.
    Sem uma pergunta como esta, o sistema não teria como distinguir "não foi
    criada" de "foi criada e eu não fiquei sabendo" — e a segunda tentativa
    geraria uma segunda cobrança para o mesmo cliente.

    Devolve o dict da cobrança, `None` quando não existe nenhuma, ou um dict
    com '_erro' quando a própria consulta falhou. Os três casos são
    diferentes e quem chama precisa tratá-los separadamente: em caso de erro,
    emitir de novo seria justamente o risco que este mecanismo evita.
    """
    from urllib.parse import quote

    resultado = _request_get(f"/payments?externalReference={quote(str(referencia_externa))}")
    if resultado.get('_erro'):
        return resultado
    dados = resultado.get('data') or []
    return dados[0] if dados else None


def obter_status_pagamento(asaas_payment_id):
    """Retorna apenas o status de uma cobrança."""
    return _request_get(f"/payments/{asaas_payment_id}/status")


def cancelar_pagamento(asaas_payment_id):
    """Cancela uma cobrança pendente (não paga)."""
    return _request_delete(f"/payments/{asaas_payment_id}")
