# backend/blueprints/webhook.py
"""Blueprint de webhook Asaas."""
import json
import logging
import hmac
import hashlib
from flask import Blueprint, request, jsonify

import database
import asaas
import config

log = logging.getLogger("adri.webhook")

webhook_bp = Blueprint('webhook', __name__, url_prefix='/api/pagamentos')


def _validar_assinatura_asaas(payload: bytes, assinatura: str) -> bool:
    """Valida a assinatura HMAC SHA256 do webhook Asaas."""
    if not assinatura or not config.ASAAS_API_KEY:
        return False
    expected = hmac.new(
        config.ASAAS_API_KEY.encode('utf-8'),
        payload,
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, assinatura)


@webhook_bp.route('/webhook', methods=['POST'])
def webhook_asaas():
    """Endpoint para webhooks do Asaas (confirmacao de pagamento)."""
    assinatura = request.headers.get('asaas-signature', '')
    payload_bytes = request.get_data()
    if not _validar_assinatura_asaas(payload_bytes, assinatura):
        log.warning("[WEBHOOK] Assinatura invalida ou ausente.")
        return jsonify({"erro": "Assinatura invalida"}), 401

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