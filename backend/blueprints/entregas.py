# backend/blueprints/entregas.py
"""Blueprint de entregas agendadas."""
import logging
from flask import Blueprint, request, jsonify

import database
import validators
from erp.comercial import estados, repositorio

log = logging.getLogger("adri.entregas")

entregas_bp = Blueprint('entregas', __name__, url_prefix='/api/entregas')


def _validar_vinculo_com_pedido(pedido_id, cliente_id):
    """
    Devolve `(mensagem, status)` quando o vinculo nao serve, ou `(None, None)`.

    A regra de quais situacoes aceitam entrega mora em `estados.aceita_entrega`
    e e consultada aqui em vez de repetida: duas copias divergem, e a que
    diverge e sempre a que ninguem lembra de atualizar.
    """
    with database.conectar() as conexao:
        pedido = repositorio.obter_pedido(conexao, pedido_id)

    if pedido is None:
        return "Pedido nao encontrado.", 404
    if int(pedido['cliente_id']) != int(cliente_id):
        return "O pedido informado e de outro cliente.", 409
    if not estados.aceita_entrega(pedido['situacao']):
        return (f"O pedido {pedido['numero']} esta em '{pedido['situacao']}' "
                "e nao aceita entrega."), 409
    return None, None


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

    # O pedido vinculado precisa ser DAQUELE cliente e estar numa situacao que
    # ainda espera entrega.
    #
    # `validar_entrega` so conferia que `pedido_id` e inteiro positivo, e a FK
    # so garante que o pedido existe. Dava para agendar entrega do cliente B
    # apontando para o pedido do cliente A -- ou para um rascunho, ou para um
    # pedido cancelado. O mesmo cuidado ja existia para o NOME do cliente (que
    # vem do cadastro, e nao do corpo, logo abaixo); faltava para o pedido.
    if entrega.get('pedido_id'):
        erro, status = _validar_vinculo_com_pedido(
            entrega['pedido_id'], entrega['cliente_id'])
        if erro:
            return jsonify({"erro": erro}), status

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