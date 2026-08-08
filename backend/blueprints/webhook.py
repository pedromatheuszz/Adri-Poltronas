# backend/blueprints/webhook.py
"""Blueprint de webhook Asaas."""
import json
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
    log.info("[WEBHOOK] Recebido: %s", json.dumps(dados, ensure_ascii=False)[:500])
    tipo_evento = dados.get('event', '')
    pagamento_asaas = dados.get('payment', {})
    asaas_payment_id = pagamento_asaas.get('id', '')
    if not asaas_payment_id:
        return jsonify({"mensagem": "OK"}), 200
    if tipo_evento in ('PAYMENT_RECEIVED', 'PAYMENT_CONFIRMED'):
        with database.conectar() as conexao:
            pagamento = conexao.execute(
                'SELECT * FROM pagamentos WHERE asaas_payment_id=?', (asaas_payment_id,)
            ).fetchone()
            if pagamento:
                conexao.execute(
                    'UPDATE pagamentos SET status="Recebido", data_pagamento=datetime("now", "localtime") WHERE asaas_payment_id=?',
                    (asaas_payment_id,)
                )
                conexao.execute(
                    'INSERT INTO historico (cliente_id, cliente_nome, acao, detalhes) VALUES (?, ?, ?, ?)',
                    (pagamento['cliente_id'], pagamento['cliente_nome'], 'PAGAMENTO',
                     f'Pagamento confirmado via webhook: R$ {pagamento["valor"]:.2f}'),
                )
                log.info("[WEBHOOK] Pagamento %s confirmado via Asaas.", asaas_payment_id)
    elif tipo_evento == 'PAYMENT_OVERDUE':
        with database.conectar() as conexao:
            conexao.execute(
                'UPDATE pagamentos SET status="Atrasado" WHERE asaas_payment_id=? AND status="Pendente"',
                (asaas_payment_id,)
            )
    elif tipo_evento == 'PAYMENT_DELETED':
        with database.conectar() as conexao:
            conexao.execute(
                'UPDATE pagamentos SET status="Cancelado" WHERE asaas_payment_id=?',
                (asaas_payment_id,)
            )
    return jsonify({"mensagem": "OK"}), 200