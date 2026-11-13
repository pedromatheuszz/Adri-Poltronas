# backend/blueprints/notificacoes.py
"""Blueprint de notificações inteligentes."""
import logging
from flask import Blueprint, request, jsonify

import database
from permissoes import exigir_permissao

log = logging.getLogger("adri.notificacoes")

notificacoes_bp = Blueprint('notificacoes', __name__, url_prefix='/api')


@notificacoes_bp.route('/notificacoes')
@exigir_permissao("notificacoes.ver")
def api_obter_notificacoes():
    """Retorna notificacoes do sistema, com a contagem de nao lidas."""
    try:
        notifs = database.obter_notificacoes()
        nao_lidas = sum(1 for n in notifs if not n.get('lida'))
        return jsonify({
            "notificacoes": notifs,
            "total": len(notifs),
            "nao_lidas": nao_lidas,
        })
    except Exception:
        log.exception("Erro ao obter notificacoes")
        return jsonify({
            "notificacoes": [], "total": 0, "nao_lidas": 0,
            "erro": "Nao foi possivel carregar as notificacoes.",
        }), 500


@notificacoes_bp.route('/notificacoes/lidas', methods=['POST'])
@exigir_permissao("notificacoes.gerenciar")
def api_marcar_lidas():
    """
    Marca notificacoes como lidas.

    Corpo: {"chaves": ["pagamento_atrasado:3", ...]}
           {"todas": true} marca tudo que esta ativo no momento.
    """
    dados = request.get_json(silent=True) or {}

    if dados.get('todas'):
        chaves = [n['chave'] for n in database.obter_notificacoes() if n.get('chave')]
    else:
        chaves = dados.get('chaves') or []
        if not isinstance(chaves, list):
            return jsonify({"erro": "Campo 'chaves' deve ser uma lista."}), 400

    quantidade = database.marcar_notificacoes_lidas(chaves)
    return jsonify({"mensagem": "Notificacoes marcadas como lidas.", "quantidade": quantidade})


@notificacoes_bp.route('/notificacoes/lidas', methods=['DELETE'])
@exigir_permissao("notificacoes.gerenciar")
def api_desmarcar_lidas():
    """Volta notificacoes para nao lidas. Sem corpo, restaura todas."""
    dados = request.get_json(silent=True) or {}
    chaves = dados.get('chaves')
    if chaves is not None and not isinstance(chaves, list):
        return jsonify({"erro": "Campo 'chaves' deve ser uma lista."}), 400

    quantidade = database.desmarcar_notificacoes_lidas(chaves)
    return jsonify({"mensagem": "Notificacoes restauradas.", "quantidade": quantidade})
