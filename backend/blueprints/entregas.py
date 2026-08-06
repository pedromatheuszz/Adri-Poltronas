# backend/blueprints/entregas.py
"""Blueprint de entregas agendadas."""
import logging
from flask import Blueprint, request, jsonify

import database

log = logging.getLogger("adri.entregas")

entregas_bp = Blueprint('entregas', __name__, url_prefix='/api/entregas')


@entregas_bp.route('', methods=['GET'])
def listar_entregas():
    """Lista entregas agendadas."""
    status = request.args.get('status')
    return jsonify(database.listar_entregas_agendadas(status=status))


@entregas_bp.route('', methods=['POST'])
def criar_entrega():
    """Agenda uma nova entrega."""
    dados = request.get_json(silent=True) or {}
    cliente_id = dados.get('cliente_id')
    cliente_nome = dados.get('cliente_nome', '')
    data_entrega = dados.get('data_entrega', '')
    hora_entrega = dados.get('hora_entrega', '')
    descricao = dados.get('descricao', '')
    if not cliente_id or not data_entrega:
        return jsonify({"erro": "cliente_id e data_entrega sao obrigatorios."}), 400
    entrega_id = database.agendar_entrega(cliente_id, cliente_nome, data_entrega, hora_entrega, descricao)
    return jsonify({"mensagem": "Entrega agendada!", "id": entrega_id}), 201


@entregas_bp.route('/<int:entrega_id>/status', methods=['PUT'])
def atualizar_status_entrega(entrega_id):
    """Atualiza status de uma entrega."""
    dados = request.get_json(silent=True) or {}
    novo_status = dados.get('status', '')
    if novo_status not in ('Pendente', 'Em andamento', 'Concluida', 'Cancelada'):
        return jsonify({"erro": "Status invalido."}), 400
    linhas = database.atualizar_status_entrega(entrega_id, novo_status)
    if linhas == 0:
        return jsonify({"erro": "Entrega nao encontrada."}), 404
    return jsonify({"mensagem": "Status atualizado!"}), 200