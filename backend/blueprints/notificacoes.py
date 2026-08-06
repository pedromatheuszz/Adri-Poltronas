# backend/blueprints/notificacoes.py
"""Blueprint de notificações inteligentes."""
import logging
from flask import Blueprint, jsonify

import database

log = logging.getLogger("adri.notificacoes")

notificacoes_bp = Blueprint('notificacoes', __name__, url_prefix='/api')


@notificacoes_bp.route('/notificacoes')
def api_obter_notificacoes():
    """Retorna notificacoes inteligentes do sistema."""
    try:
        notifs = database.obter_notificacoes()
        return jsonify({"notificacoes": notifs, "total": len(notifs)})
    except Exception as e:
        log.exception("Erro ao obter notificacoes")
        return jsonify({"notificacoes": [], "total": 0, "erro": str(e)}), 500