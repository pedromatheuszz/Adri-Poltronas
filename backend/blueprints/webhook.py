# backend/blueprints/webhook.py
"""
Blueprint de webhook Asaas.

Nota sobre o SQL daqui: literais de string usam aspas SIMPLES. Aspas duplas
funcionavam por acidente -- o SQLite so as trata como string quando nao existe
coluna com aquele nome, uma extensao de compatibilidade que pode ser desligada
(SQLITE_DQS=0). Com uma coluna chamada `Recebido`, o UPDATE viraria outra coisa
silenciosamente.
"""
import logging
import hmac
from flask import Blueprint, request, jsonify

import database
import config

log = logging.getLogger("adri.webhook")

webhook_bp = Blueprint('webhook', __name__, url_prefix='/api/pagamentos')


def _token_valido(token_recebido: str) -> bool:
    """
    Valida o token de autenticacao do webhook Asaas.

    O Asaas nao assina o payload: ele envia, no header `asaas-access-token`,
    o token estatico definido no momento em que o webhook foi cadastrado.
    A comparacao e feita em tempo constante para nao vazar o token por timing.
    """
    esperado = config.ASAAS_WEBHOOK_TOKEN
    if not esperado or not token_recebido:
        return False
    return hmac.compare_digest(esperado, token_recebido)


@webhook_bp.route('/webhook', methods=['POST'])
def webhook_asaas():
    """Endpoint para webhooks do Asaas (confirmacao de pagamento)."""
    if not config.ASAAS_WEBHOOK_TOKEN:
        # Fail closed: sem token configurado nao ha como distinguir o Asaas de
        # um terceiro, e o efeito seria marcar cobrancas como pagas.
        log.error("[WEBHOOK] ASAAS_WEBHOOK_TOKEN nao configurado. Requisicao recusada.")
        return jsonify({"erro": "Webhook nao configurado."}), 503

    if not _token_valido(request.headers.get('asaas-access-token', '')):
        log.warning("[WEBHOOK] Token de autenticacao invalido ou ausente.")
        return jsonify({"erro": "Nao autorizado"}), 401

    dados = request.get_json(silent=True) or {}
    tipo_evento = dados.get('event', '')
    pagamento_asaas = dados.get('payment', {})
    asaas_payment_id = pagamento_asaas.get('id', '')
    log.info(
        "[WEBHOOK] Evento Asaas recebido: tipo=%s pagamento=%s",
        tipo_evento,
        asaas_payment_id,
    )
    if not asaas_payment_id:
        return jsonify({"mensagem": "OK"}), 200
    if tipo_evento in ('PAYMENT_RECEIVED', 'PAYMENT_CONFIRMED'):
        alterado = database.atualizar_pagamento_por_asaas(
            asaas_payment_id,
            'Recebido',
            preencher_data_pagamento=True,
        )
        if alterado:
            log.info("[WEBHOOK] Pagamento %s confirmado via Asaas.", asaas_payment_id)
    elif tipo_evento == 'PAYMENT_OVERDUE':
        database.atualizar_pagamento_por_asaas(
            asaas_payment_id,
            'Atrasado',
            status_anterior='Pendente',
        )
    elif tipo_evento == 'PAYMENT_DELETED':
        database.atualizar_pagamento_por_asaas(asaas_payment_id, 'Cancelado')
    return jsonify({"mensagem": "OK"}), 200
