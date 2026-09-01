"""
Fixtures do backend v2.

Banco temporario por teste: nenhum teste ve o estado deixado por outro, e a
suite nunca toca no banco real. No v1 a fixture reescrevia `database.DB_PATH`,
uma variavel global de modulo -- o que so funciona enquanto ninguem roda em
paralelo.
"""
from __future__ import annotations

import os
import pathlib
import sys
import tempfile

import pytest

# A RAIZ do repositorio no path -- nao `backend_v2`. O v2 e um pacote e se
# resolve pelo proprio nome, entao `backend_v2.app` nunca disputa o nome `app`
# com o modulo de topo do v1. E o que permite as duas suites no mesmo processo.
RAIZ = pathlib.Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from backend_v2.banco import conexao as banco                      # noqa: E402
from backend_v2.nucleo.unidade_trabalho import UnidadeDeTrabalho   # noqa: E402
from backend_v2.app import criar_app                               # noqa: E402


@pytest.fixture
def caminho_banco():
    descritor, caminho = tempfile.mkstemp(suffix='.db')
    os.close(descritor)
    os.unlink(caminho)
    banco.preparar_banco(caminho)
    yield caminho
    for sufixo in ('', '-wal', '-shm'):
        try:
            os.unlink(caminho + sufixo)
        except OSError:
            pass


@pytest.fixture
def fabrica(caminho_banco):
    return lambda: banco.conectar(caminho_banco)


@pytest.fixture
def uow(fabrica):
    """Abre uma unidade de trabalho nova a cada chamada."""
    def abrir():
        return UnidadeDeTrabalho(fabrica)
    return abrir


@pytest.fixture
def app(caminho_banco):
    aplicacao = criar_app(caminho_banco)
    aplicacao.config['TESTING'] = True
    return aplicacao


@pytest.fixture
def cliente_http(app):
    return app.test_client()


# ---------------------------------------------------------------------------
# Massa de dados
# ---------------------------------------------------------------------------
@pytest.fixture
def dados_base(uow):
    """Fornecedor, cliente, produto estocavel, servico e uma conta de caixa."""
    from backend_v2.aplicacao import cadastro, catalogo, financeiro

    with uow() as u:
        fornecedor = cadastro.criar(u, {
            'nome': 'Estofados Sul Ltda', 'documento': '11.222.333/0001-81',
            'e_cliente': False, 'e_fornecedor': True, 'cidade': 'Joinville', 'uf': 'SC',
        })
        cliente = cadastro.criar(u, {
            'nome': 'Doraci Pereira da Silva', 'documento': '529.982.247-25',
            'cidade': 'Joinville', 'uf': 'SC', 'cep': '89230-210',
        })
        poltrona = catalogo.criar(u, {
            'codigo': 'PLT-001', 'descricao': 'Poltrona Reclinavel',
            'preco_venda': '1.890,00', 'estoque_minimo': 2,
        })
        servico = catalogo.criar(u, {
            'codigo': 'SRV-FRETE', 'descricao': 'Frete e montagem',
            'preco_venda': '150,00', 'controla_estoque': False,
        })
        conta = financeiro.criar_conta(u, {
            'nome': 'Caixa Loja', 'tipo': 'caixa', 'saldo_inicial': '0,00',
        })
    return {
        'fornecedor': fornecedor, 'cliente': cliente,
        'poltrona': poltrona, 'servico': servico, 'conta': conta,
    }


@pytest.fixture
def com_estoque(uow, dados_base):
    """Recebe uma compra de 10 poltronas a R$ 900,00 -- estoque e custo prontos."""
    from backend_v2.aplicacao import compras

    with uow() as u:
        compra = compras.criar(u, {
            'parceiro_id': dados_base['fornecedor']['id'],
            'itens': [{'produto_id': dados_base['poltrona']['id'],
                       'quantidade': 10, 'preco_unitario': '900,00'}],
        })
        compras.abrir(u, compra['id'])
        compras.receber(u, compra['id'],
                        {'parcelas': 1, 'primeiro_vencimento': '2026-12-01'})
    return dados_base
