"""
Cliente do Mercado Pago -- usado APENAS para a licenca do proprio aplicativo.

Nao confundir com `asaas.py`
----------------------------
O Asaas cobra os CLIENTES da Adri: locacao de poltrona, Pix e boleto do
negocio. Este modulo cobra UMA coisa so, uma vez so: a licenca de uso do
aplicativo, paga pela Adri ao autor. Sao contas, credenciais e ciclos de vida
diferentes, e junta-los num modulo so significaria que um erro na cobranca da
licenca poderia derrubar a cobranca do negocio.

O limite honesto desta integracao
---------------------------------
A verificacao automatica do pagamento exige o `access_token` da conta do
VENDEDOR, e esse token da acesso total a ela -- criar cobranca, ler
movimentacao, estornar. Ele fica na maquina do CLIENTE, cifrado com DPAPI
junto das demais credenciais.

Cifrar prende o token a conta do Windows daquela maquina e impede que ele seja
copiado para outra. Nao impede quem tem administrador ali de extrai-lo. A
forma correta de fechar isso e um endpoint do vendedor que responda apenas
"esta licenca esta paga?" -- o app perguntaria a ele, e nao ao Mercado Pago,
e nenhum token do vendedor sairia da casa dele. Enquanto esse endpoint nao
existe, a recomendacao pratica e usar um token de aplicacao dedicada a este
fim, e nao o token principal da conta.

Por que consulta, e nao webhook
-------------------------------
Pelo mesmo motivo que `erp/financeiro/reconciliacao.py` documenta para o
Asaas: o Flask escuta em 127.0.0.1 e um servidor na internet nao alcanca o
loopback da maquina do usuario. Perguntar de dentro para fora atravessa
qualquer firewall e nao expoe nada.
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
import uuid

import segredos

_log = logging.getLogger("adri.mercadopago")

NOME_DO_TOKEN = "MP_ACCESS_TOKEN"
NOME_DA_URL = "MP_API_URL"

URL_PADRAO = "https://api.mercadopago.com"
TIMEOUT_S = 15


def url_base() -> str:
    """
    Endereco da API. Configuravel pelo mesmo motivo que `asaas.py` alterna
    entre sandbox e producao: para conseguir exercitar o fluxo inteiro --
    gerar a cobranca, esperar, receber a confirmacao -- sem mexer com dinheiro
    de verdade.

    Vazio ou ausente significa producao. Nao ha "modo de teste" implicito: uma
    instalacao que nao configurou nada fala com o Mercado Pago de verdade, que
    e o comportamento que nao surpreende ninguem.
    """
    return (segredos.obter(NOME_DA_URL) or "").strip() or URL_PADRAO

# Estados do Mercado Pago que significam "o dinheiro entrou".
#
# `authorized` NAO esta aqui de proposito: e cartao autorizado e ainda nao
# capturado, ou seja, dinheiro reservado e nao recebido. Liberar a licenca ali
# entregaria o produto por uma transacao que ainda pode nao se concretizar.
STATUS_PAGOS = frozenset({"approved"})

# Estados terminais que nao viram pagamento. Servem para a interface parar de
# perguntar em vez de girar para sempre.
STATUS_ENCERRADOS = frozenset({"cancelled", "rejected", "refunded", "charged_back"})


def token() -> str:
    return (segredos.obter(NOME_DO_TOKEN) or "").strip()


def esta_configurado() -> bool:
    return bool(token())


def _cabecalhos(idempotencia: str = "") -> dict:
    cabecalhos = {
        "Authorization": f"Bearer {token()}",
        "Content-Type": "application/json",
        "User-Agent": "AdriPoltronas/licenca",
    }
    if idempotencia:
        # O Mercado Pago exige a chave em POST /v1/payments. Sem ela, um
        # clique duplo ou uma repeticao por timeout cria DUAS cobrancas da
        # licenca -- e a segunda seria dinheiro cobrado a mais de quem ja
        # pagou.
        cabecalhos["X-Idempotency-Key"] = idempotencia
    return cabecalhos


def _resumo_do_erro(corpo: str) -> str:
    """
    O que vai para o log quando o Mercado Pago recusa.

    Mesma regra adotada em `asaas.py`: codigo e mensagem curta, nunca o corpo
    bruto, que repete o que foi enviado.
    """
    try:
        detalhe = json.loads(corpo)
    except (ValueError, TypeError):
        return f"<sem JSON; {len(corpo)} bytes no corpo>"
    if not isinstance(detalhe, dict):
        return "<corpo inesperado>"
    partes = [str(detalhe.get(campo)) for campo in ("status", "error", "message")
              if detalhe.get(campo)]
    return ", ".join(partes) if partes else "<sem codigo no corpo>"


def _executar(requisicao, descricao: str) -> dict:
    try:
        with urllib.request.urlopen(requisicao, timeout=TIMEOUT_S) as resposta:
            bruto = resposta.read().decode("utf-8")
            return json.loads(bruto) if bruto else {}
    except urllib.error.HTTPError as erro:
        corpo = erro.read().decode("utf-8", errors="replace")
        _log.error("Mercado Pago %s -> %s: %s", descricao, erro.code,
                   _resumo_do_erro(corpo))
        return {"_erro": True, "_status": erro.code}
    except Exception as erro:
        _log.exception("Mercado Pago %s: falha de conexao", descricao)
        return {"_erro": True, "_detalhe": str(erro)}


def criar_cobranca_pix(valor_centavos: int, descricao: str, referencia: str,
                       email_do_pagador: str = "") -> dict:
    """
    Cria uma cobranca Pix da licenca e devolve o que a tela precisa mostrar.

    `referencia` vai como `external_reference` e liga o pagamento a ESTA
    instalacao: e o que permite, depois, perguntar ao Mercado Pago se aquela
    cobranca especifica foi paga.
    """
    if not esta_configurado():
        return {"_erro": True, "_detalhe": "Mercado Pago nao configurado."}

    corpo = {
        "transaction_amount": round(valor_centavos / 100, 2),
        "description": descricao,
        "payment_method_id": "pix",
        "external_reference": referencia,
        "payer": {"email": email_do_pagador or "licenca@adripoltronas.local"},
    }
    requisicao = urllib.request.Request(
        f"{url_base()}/v1/payments",
        data=json.dumps(corpo).encode("utf-8"),
        # A chave de idempotencia deriva da referencia da instalacao mais um
        # sorteio: repetir a MESMA tentativa nao cobra duas vezes, e uma nova
        # tentativa deliberada (a cobranca anterior expirou) ainda e possivel.
        headers=_cabecalhos(f"{referencia}-{uuid.uuid4().hex[:12]}"),
        method="POST",
    )
    resposta = _executar(requisicao, "POST /v1/payments")
    if resposta.get("_erro"):
        return resposta

    interacao = (resposta.get("point_of_interaction") or {}).get("transaction_data") or {}
    return {
        "pagamento_id": str(resposta.get("id") or ""),
        "status": resposta.get("status") or "",
        "pix_payload": interacao.get("qr_code") or "",
        "pix_qr_code": interacao.get("qr_code_base64") or "",
        "expira_em": resposta.get("date_of_expiration") or "",
    }


def obter_pagamento(pagamento_id: str) -> dict:
    """Estado atual de uma cobranca. E o que substitui o webhook."""
    if not esta_configurado():
        return {"_erro": True, "_detalhe": "Mercado Pago nao configurado."}
    if not pagamento_id:
        return {"_erro": True, "_detalhe": "Sem pagamento a consultar."}

    caminho = urllib.parse.quote(str(pagamento_id), safe="")
    requisicao = urllib.request.Request(
        f"{url_base()}/v1/payments/{caminho}",
        headers=_cabecalhos(),
        method="GET",
    )
    resposta = _executar(requisicao, f"GET /v1/payments/{caminho}")
    if resposta.get("_erro"):
        return resposta

    status = (resposta.get("status") or "").lower()
    return {
        "pagamento_id": str(resposta.get("id") or pagamento_id),
        "status": status,
        "pago": status in STATUS_PAGOS,
        "encerrado": status in STATUS_ENCERRADOS,
        "referencia": resposta.get("external_reference") or "",
    }
