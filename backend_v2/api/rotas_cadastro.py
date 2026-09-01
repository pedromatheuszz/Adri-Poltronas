"""Rotas de parceiros, produtos e estoque."""
from __future__ import annotations

from flask import Blueprint

from backend_v2.aplicacao import cadastro, catalogo, estoque
from .comum import argumento, corpo, ok, pagina, paginado, transacional

bp_parceiros = Blueprint('parceiros', __name__, url_prefix='/api/v2/parceiros')
bp_produtos = Blueprint('produtos', __name__, url_prefix='/api/v2/produtos')
bp_estoque = Blueprint('estoque', __name__, url_prefix='/api/v2/estoque')


# ---------------------------------------------------------------------------
# Parceiros
# ---------------------------------------------------------------------------
@bp_parceiros.get('')
@transacional
def listar_parceiros(u):
    pag = pagina()
    return paginado(
        cadastro.listar(u, busca=argumento('busca'), papel=argumento('papel'),
                        cidade=argumento('cidade'), pagina=pag),
        pag,
    )


@bp_parceiros.get('/<int:identificador>')
@transacional
def obter_parceiro(u, identificador):
    return ok(cadastro.obter(u, identificador))


@bp_parceiros.post('')
@transacional
def criar_parceiro(u):
    return ok(cadastro.criar(u, corpo()), 201)


@bp_parceiros.put('/<int:identificador>')
@transacional
def atualizar_parceiro(u, identificador):
    return ok(cadastro.atualizar(u, identificador, corpo()))


@bp_parceiros.delete('/<int:identificador>')
@transacional
def inativar_parceiro(u, identificador):
    cadastro.inativar(u, identificador)
    return ok({"mensagem": "Parceiro inativado."})


# ---------------------------------------------------------------------------
# Produtos
# ---------------------------------------------------------------------------
@bp_produtos.get('')
@transacional
def listar_produtos(u):
    pag = pagina()
    return paginado(
        catalogo.listar(u, busca=argumento('busca'),
                        apenas_estocaveis=argumento('estocaveis') == '1', pagina=pag),
        pag,
    )


@bp_produtos.get('/<int:identificador>')
@transacional
def obter_produto(u, identificador):
    return ok(catalogo.obter(u, identificador))


@bp_produtos.post('')
@transacional
def criar_produto(u):
    return ok(catalogo.criar(u, corpo()), 201)


@bp_produtos.put('/<int:identificador>')
@transacional
def atualizar_produto(u, identificador):
    return ok(catalogo.atualizar(u, identificador, corpo()))


@bp_produtos.delete('/<int:identificador>')
@transacional
def inativar_produto(u, identificador):
    catalogo.inativar(u, identificador)
    return ok({"mensagem": "Produto inativado."})


# ---------------------------------------------------------------------------
# Estoque
# ---------------------------------------------------------------------------
@bp_estoque.get('/saldos')
@transacional
def listar_saldos(u):
    pag = pagina()
    return paginado(
        estoque.listar_saldos(u, apenas_abaixo_do_minimo=argumento('abaixo_minimo') == '1',
                              pagina=pag),
        pag,
    )


@bp_estoque.get('/saldos/<int:produto_id>')
@transacional
def saldo_do_produto(u, produto_id):
    return ok(estoque.saldo(u, produto_id))


@bp_estoque.get('/movimentos/<int:produto_id>')
@transacional
def historico_do_produto(u, produto_id):
    pag = pagina()
    return paginado(estoque.historico(u, produto_id, pagina=pag), pag)


@bp_estoque.post('/ajustes')
@transacional
def ajustar_estoque(u):
    return ok(estoque.ajustar(u, corpo()), 201)


@bp_estoque.post('/movimentos/<int:movimento_id>/estorno')
@transacional
def estornar_movimento(u, movimento_id):
    return ok(estoque.estornar_movimento(u, movimento_id, corpo().get('motivo', '')), 201)
