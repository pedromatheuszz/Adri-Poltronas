# backend/blueprints/entregas.py
"""Blueprint de entregas agendadas."""
import logging
from flask import Blueprint, request, jsonify

import database
import validators

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
    entrega, erros = validators.validar_entrega(request.get_json(silent=True) or {})
    if erros:
        return jsonify({"erro": "Dados invalidos.", "detalhes": erros}), 400

    cliente = database.obter_cliente_por_id(entrega['cliente_id'])
    if not cliente:
        return jsonify({"erro": "Cliente nao encontrado."}), 404

    # O nome vem do cadastro, e nao do corpo da requisicao: era possivel
    # agendar para o cliente 7 gravando o nome de outro, e a notificacao
    # avisaria a pessoa errada.
    entrega_id = database.agendar_entrega(
        entrega['cliente_id'], cliente['nome'], entrega['data_entrega'],
        entrega['hora_entrega'], entrega['descricao'], entrega.get('pedido_id'),
    )
    return jsonify({"mensagem": "Entrega agendada!", "id": entrega_id}), 201


@entregas_bp.route('/<int:entrega_id>/status', methods=['PUT'])
def atualizar_status_entrega(entrega_id):
    """Atualiza status de uma entrega."""
    dados = request.get_json(silent=True) or {}
    novo_status = dados.get('status', '')
    if novo_status not in validators.OPCOES_STATUS_ENTREGA:
        return jsonify({"erro": "Status invalido."}), 400
    linhas = database.atualizar_status_entrega(entrega_id, novo_status)
    if linhas == 0:
        return jsonify({"erro": "Entrega nao encontrada."}), 404
    return jsonify({"mensagem": "Status atualizado!"}), 200