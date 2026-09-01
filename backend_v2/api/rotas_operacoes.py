"""Rotas de vendas, compras e financeiro."""
from __future__ import annotations

from flask import Blueprint

from backend_v2.aplicacao import compras, financeiro, vendas
from .comum import argumento, corpo, ok, pagina, paginado, transacional

bp_vendas = Blueprint('vendas', __name__, url_prefix='/api/v2/vendas')
bp_compras = Blueprint('compras', __name__, url_prefix='/api/v2/compras')
bp_financeiro = Blueprint('financeiro', __name__, url_prefix='/api/v2/financeiro')


# ---------------------------------------------------------------------------
# Vendas
# ---------------------------------------------------------------------------
@bp_vendas.get('')
@transacional
def listar_vendas(u):
    pag = pagina()
    return paginado(
        vendas.listar(u, situacao=argumento('situacao'), especie=argumento('especie'),
                      parceiro_id=argumento('parceiro_id') or None,
                      de=argumento('de'), ate=argumento('ate'), pagina=pag),
        pag,
    )


@bp_vendas.get('/<int:identificador>')
@transacional
def obter_venda(u, identificador):
    return ok(vendas.obter(u, identificador))


@bp_vendas.post('')
@transacional
def criar_venda(u):
    return ok(vendas.criar(u, corpo()), 201)


@bp_vendas.post('/<int:identificador>/itens')
@transacional
def adicionar_item_venda(u, identificador):
    return ok(vendas.adicionar_item(u, identificador, corpo()), 201)


@bp_vendas.delete('/<int:identificador>/itens')
@transacional
def limpar_itens_venda(u, identificador):
    return ok(vendas.remover_itens(u, identificador))


# As transicoes sao POST em sub-recurso, e nao PUT no campo `situacao`. Deixar
# o cliente escrever a situacao direto e o que permite pular etapas -- ir de
# 'rascunho' a 'faturado' sem passar pelas regras de cada passo.
@bp_vendas.post('/<int:identificador>/abertura')
@transacional
def abrir_venda(u, identificador):
    return ok(vendas.abrir(u, identificador))


@bp_vendas.post('/<int:identificador>/aprovacao')
@transacional
def aprovar_venda(u, identificador):
    return ok(vendas.aprovar(u, identificador))


@bp_vendas.post('/<int:identificador>/faturamento')
@transacional
def faturar_venda(u, identificador):
    return ok(vendas.faturar(u, identificador, corpo()), 201)


@bp_vendas.post('/<int:identificador>/cancelamento')
@transacional
def cancelar_venda(u, identificador):
    return ok(vendas.cancelar(u, identificador, corpo().get('motivo', '')))


# ---------------------------------------------------------------------------
# Compras
# ---------------------------------------------------------------------------
@bp_compras.get('')
@transacional
def listar_compras(u):
    pag = pagina()
    return paginado(
        compras.listar(u, situacao=argumento('situacao'),
                       parceiro_id=argumento('parceiro_id') or None,
                       de=argumento('de'), ate=argumento('ate'), pagina=pag),
        pag,
    )


@bp_compras.get('/<int:identificador>')
@transacional
def obter_compra(u, identificador):
    return ok(compras.obter(u, identificador))


@bp_compras.post('')
@transacional
def criar_compra(u):
    return ok(compras.criar(u, corpo()), 201)


@bp_compras.post('/<int:identificador>/itens')
@transacional
def adicionar_item_compra(u, identificador):
    return ok(compras.adicionar_item(u, identificador, corpo()), 201)


@bp_compras.post('/<int:identificador>/abertura')
@transacional
def abrir_compra(u, identificador):
    return ok(compras.abrir(u, identificador))


@bp_compras.post('/<int:identificador>/recebimento')
@transacional
def receber_compra(u, identificador):
    return ok(compras.receber(u, identificador, corpo()), 201)


@bp_compras.post('/<int:identificador>/cancelamento')
@transacional
def cancelar_compra(u, identificador):
    return ok(compras.cancelar(u, identificador, corpo().get('motivo', '')))


# ---------------------------------------------------------------------------
# Financeiro
# ---------------------------------------------------------------------------
@bp_financeiro.get('/titulos')
@transacional
def listar_titulos(u):
    pag = pagina()
    return paginado(
        financeiro.listar_titulos(
            u, natureza=argumento('natureza'), situacao=argumento('situacao'),
            parceiro_id=argumento('parceiro_id') or None,
            vence_de=argumento('vence_de'), vence_ate=argumento('vence_ate'), pagina=pag),
        pag,
    )


@bp_financeiro.get('/titulos/<int:identificador>')
@transacional
def obter_titulo(u, identificador):
    return ok(financeiro.obter_titulo(u, identificador))


@bp_financeiro.post('/titulos')
@transacional
def criar_titulo(u):
    return ok({"titulos": financeiro.criar_titulo_avulso(u, corpo())}, 201)


@bp_financeiro.post('/titulos/<int:identificador>/baixas')
@transacional
def baixar_titulo(u, identificador):
    return ok(financeiro.baixar(u, identificador, corpo()), 201)


@bp_financeiro.post('/titulos/<int:identificador>/cancelamento')
@transacional
def cancelar_titulo(u, identificador):
    return ok(financeiro.cancelar_titulo(u, identificador, corpo().get('motivo', '')))


@bp_financeiro.post('/baixas/<int:baixa_id>/estorno')
@transacional
def estornar_baixa(u, baixa_id):
    return ok(financeiro.estornar_baixa(u, baixa_id, corpo().get('motivo', '')), 201)


@bp_financeiro.get('/contas')
@transacional
def listar_contas(u):
    return ok(financeiro.listar_contas(u))


@bp_financeiro.post('/contas')
@transacional
def criar_conta(u):
    return ok(financeiro.criar_conta(u, corpo()), 201)


@bp_financeiro.get('/extrato')
@transacional
def extrato(u):
    pag = pagina()
    return paginado(
        financeiro.extrato(u, conta_id=argumento('conta_id') or None,
                           de=argumento('de'), ate=argumento('ate'), pagina=pag),
        pag,
    )
