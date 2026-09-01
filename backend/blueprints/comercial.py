# backend/blueprints/comercial.py
"""
Blueprint do catalogo e dos pedidos de venda.

Adaptador HTTP puro: traduz JSON para chamada de caso de uso e erro de dominio
para status. Nenhuma regra de negocio mora aqui -- elas ficam em
`erp/comercial/servico.py`, onde podem ser testadas sem subir o Flask.

Contrato conforme API_STANDARD.md: sem envelope, erro sempre na chave `erro`.
"""
import logging
from functools import wraps

from flask import Blueprint, jsonify, request

from erp.comercial import servico

log = logging.getLogger("adri.comercial")

produtos_bp = Blueprint("produtos", __name__, url_prefix="/api/produtos")
pedidos_bp = Blueprint("pedidos", __name__, url_prefix="/api/pedidos")


def traduzir_erros(funcao):
    """
    Erro de dominio -> status HTTP, num lugar so.

    Sem isto cada rota repete o mesmo try/except de quatro ramos, e uma delas
    acaba devolvendo 500 para o que era uma regra de negocio.
    """
    @wraps(funcao)
    def interna(*args, **kwargs):
        try:
            return funcao(*args, **kwargs)
        except servico.NaoEncontrado as erro:
            return jsonify({"erro": str(erro)}), 404
        except servico.ConflitoDeSituacao as erro:
            # 409: o pedido existe e os dados sao validos -- o que nao serve e
            # a situacao em que ele esta.
            return jsonify({"erro": str(erro)}), 409
        except servico.ErroDeNegocio as erro:
            return jsonify({"erro": str(erro)}), 400
    return interna


def _corpo() -> dict:
    return request.get_json(silent=True) or {}


# =============================================================================
# Produtos
# =============================================================================
@produtos_bp.route("", methods=["GET"])
def listar_produtos():
    return jsonify(servico.listar_produtos(
        busca=request.args.get("busca", ""),
        incluir_inativos=request.args.get("incluir_inativos") == "1",
    ))


@produtos_bp.route("", methods=["POST"])
@traduzir_erros
def criar_produto():
    return jsonify(servico.criar_produto(_corpo())), 201


@produtos_bp.route("/<int:produto_id>", methods=["PUT"])
@traduzir_erros
def atualizar_produto(produto_id):
    return jsonify(servico.atualizar_produto(produto_id, _corpo()))


@produtos_bp.route("/<int:produto_id>", methods=["DELETE"])
@traduzir_erros
def inativar_produto(produto_id):
    servico.inativar_produto(produto_id)
    return jsonify({"mensagem": "Produto inativado."})


# =============================================================================
# Pedidos
# =============================================================================
@pedidos_bp.route("", methods=["GET"])
def listar_pedidos():
    return jsonify(servico.listar_pedidos(
        situacao=request.args.get("situacao", ""),
        busca=request.args.get("busca", ""),
    ))


@pedidos_bp.route("/<int:pedido_id>", methods=["GET"])
@traduzir_erros
def obter_pedido(pedido_id):
    return jsonify(servico.obter_pedido(pedido_id))


@pedidos_bp.route("", methods=["POST"])
@traduzir_erros
def criar_pedido():
    return jsonify(servico.criar_pedido(_corpo())), 201


@pedidos_bp.route("/<int:pedido_id>", methods=["PUT"])
@traduzir_erros
def atualizar_pedido(pedido_id):
    return jsonify(servico.atualizar_pedido(pedido_id, _corpo()))


@pedidos_bp.route("/<int:pedido_id>/itens", methods=["POST"])
@traduzir_erros
def adicionar_item(pedido_id):
    return jsonify(servico.adicionar_item(pedido_id, _corpo())), 201


@pedidos_bp.route("/<int:pedido_id>/itens/<int:item_id>", methods=["DELETE"])
@traduzir_erros
def remover_item(pedido_id, item_id):
    return jsonify(servico.remover_item(pedido_id, item_id))


# --- Transicoes --------------------------------------------------------------
# Rotas separadas por transicao, e nao um PATCH generico de `situacao`: cada
# uma tem pre-condicoes proprias, e um endpoint unico esconderia isso atras de
# um campo de texto.
@pedidos_bp.route("/<int:pedido_id>/abertura", methods=["POST"])
@traduzir_erros
def abrir_pedido(pedido_id):
    return jsonify(servico.abrir_pedido(pedido_id))


@pedidos_bp.route("/<int:pedido_id>/aprovacao", methods=["POST"])
@traduzir_erros
def aprovar_pedido(pedido_id):
    return jsonify(servico.aprovar_pedido(pedido_id))


@pedidos_bp.route("/<int:pedido_id>/faturamento", methods=["POST"])
@traduzir_erros
def faturar_pedido(pedido_id):
    return jsonify(servico.faturar_pedido(pedido_id, _corpo()))


@pedidos_bp.route("/<int:pedido_id>/cancelamento", methods=["POST"])
@traduzir_erros
def cancelar_pedido(pedido_id):
    return jsonify(servico.cancelar_pedido(pedido_id, _corpo().get("motivo", "")))
