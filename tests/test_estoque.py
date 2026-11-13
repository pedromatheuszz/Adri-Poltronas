"""
Estoque: o razao de quantidade e a reserva derivada dos pedidos.

O que estes testes garantem, na ordem em que o operador depende dela:

* o razao aceita so o que faz sentido fisico (aquisicao entra, baixa sai,
  estoque nunca fica negativo);
* total zero continua sendo catalogo puro -- produto sem controle nao
  bloqueia pedido, porque nunca prometeu controlar;
* a disponibilidade responde pela janela de aluguel: aprovado reserva,
  aberto apenas avisa, cancelado devolve, item sem janela ocupa sempre.
"""
import json
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

import app as app_module  # noqa: E402
import database  # noqa: E402

ORIGEM = 'http://localhost'
CABECALHOS = {'Origin': ORIGEM, 'Content-Type': 'application/json'}

# Janelas de teste no futuro distante: nada aqui depende do dia em que a
# suite roda. Duas constantes para a mesma data, DE PROPOSITO: o payload do
# item carrega os campos do item; a consulta de estoque pergunta por
# `inicio`/`fim`. Nomear igual as duas esconde a diferenca.
JANELA_ITEM = {'data_inicio_aluguel': '2030-01-01', 'data_fim_aluguel': '2030-01-15'}
OUTRA_JANELA_ITEM = {'data_inicio_aluguel': '2030-06-01', 'data_fim_aluguel': '2030-06-15'}
PERIODO = {'inicio': '2030-01-01', 'fim': '2030-01-15'}
OUTRO_PERIODO = {'inicio': '2030-06-01', 'fim': '2030-06-15'}


@pytest.fixture
def client():
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as arquivo:
        caminho = arquivo.name
    original = database.DB_PATH
    database.DB_PATH = caminho
    app_module.app.config['TESTING'] = True
    with app_module.app.app_context():
        database.criar_tabela()
    yield app_module.app.test_client()
    database.DB_PATH = original
    os.unlink(caminho)


def _post(client, rota, corpo=None):
    return client.post(rota, headers=CABECALHOS, data=json.dumps(corpo or {}))


@pytest.fixture
def cliente_id():
    return database.salvar_cliente(
        'Dona Marta', '89200-000', 'Rua A, 10', 'Centro', 'Joinville', 'Entrega')


@pytest.fixture
def produto_id(client):
    return _post(client, '/api/produtos', {
        'codigo': 'POLT-001', 'descricao': 'Poltrona Costela',
        'preco_venda': '1.850,00',
    }).get_json()['id']


def _movimento(client, produto_id, delta, tipo, motivo=''):
    return _post(client, f'/api/produtos/{produto_id}/estoque/movimentos',
                 {'delta': delta, 'tipo': tipo, 'motivo': motivo})


def _estoque(client, produto_id, **params):
    query = '&'.join(f'{k}={v}' for k, v in params.items())
    return client.get(f'/api/produtos/{produto_id}/estoque' +
                      (f'?{query}' if query else ''))


def _pedido_aprovado(client, cliente_id, produto_id, quantidade, janela):
    """Cria, lanca item e leva ate aprovado -- o estado que reserva."""
    pedido = _post(client, '/api/pedidos', {'cliente_id': cliente_id}).get_json()
    _post(client, f"/api/pedidos/{pedido['id']}/itens",
          {'produto_id': produto_id, 'quantidade': quantidade, **JANELA_ITEM})
    _post(client, f"/api/pedidos/{pedido['id']}/abertura")
    _post(client, f"/api/pedidos/{pedido['id']}/aprovacao")
    return pedido['id']


# =============================================================================
# O razao
# =============================================================================
def test_aquisicao_soma_e_aparece_no_retrato(client, produto_id):
    resposta = _movimento(client, produto_id, 3, 'aquisicao', 'Primeiras poltronas')

    assert resposta.status_code == 201
    dados = resposta.get_json()
    assert dados['total'] == 3
    assert dados['configurado'] is True
    assert dados['movimentos'][0]['motivo'] == 'Primeiras poltronas'


def test_baixa_subtrai_e_ajuste_va_para_qualquer_lado(client, produto_id):
    _movimento(client, produto_id, 3, 'aquisicao')

    assert _movimento(client, produto_id, -1, 'baixa', 'Avaria').status_code == 201
    assert _movimento(client, produto_id, +1, 'ajuste', 'Recontagem').status_code == 201
    assert _movimento(client, produto_id, -2, 'ajuste', 'Sobrou menos').status_code == 201

    # 3 - 1 + 1 - 2: o razao tem de fechar com a fisica.
    assert _estoque(client, produto_id).get_json()['total'] == 1


@pytest.mark.parametrize('corpo, fragmento', [
    ({'delta': -2, 'tipo': 'aquisicao'}, 'Aquisicao entra'),
    ({'delta': 2, 'tipo': 'baixa'}, 'Baixa sai'),
    ({'delta': 0, 'tipo': 'ajuste'}, 'diferente de zero'),
    ({'delta': 1, 'tipo': 'reforma'}, 'Tipo deve ser um de'),
    ({'tipo': 'ajuste'}, 'inteiro'),
])
def test_movimento_que_mente_sobre_a_fisica_e_recusado(client, produto_id, corpo, fragmento):
    resposta = _movimento(client, produto_id, corpo.get('delta'),
                          corpo.get('tipo'))
    assert resposta.status_code == 400
    assert fragmento in resposta.get_json()['erro']


def test_estoque_nunca_fica_negativo(client, produto_id):
    _movimento(client, produto_id, 1, 'aquisicao')

    resposta = _movimento(client, produto_id, -2, 'baixa')
    assert resposta.status_code == 400
    assert 'negativo' in resposta.get_json()['erro']


def test_movimento_de_produto_inexistente_e_404(client):
    assert _movimento(client, 999, 1, 'aquisicao').status_code == 404


# =============================================================================
# Catalogo puro: sem razao, sem checagem
# =============================================================================
def test_produto_sem_razao_continua_sendo_so_catalogo(client, cliente_id, produto_id):
    """
    Total zero e o estado das instalacoes que usam Produtos so como
    catalogo. Nenhuma checagem pode comecar a recusar item nele: o
    controle de estoque e OPT-IN, lancando o primeiro movimento.
    """
    pedido = _post(client, '/api/pedidos', {'cliente_id': cliente_id}).get_json()
    resposta = _post(client, f"/api/pedidos/{pedido['id']}/itens",
                     {'produto_id': produto_id, 'quantidade': 50})

    assert resposta.status_code == 201
    retrato = _estoque(client, produto_id).get_json()
    assert retrato['configurado'] is False
    assert retrato['total'] == 0


# =============================================================================
# A reserva derivada dos pedidos
# =============================================================================
def test_aprovado_reserva_e_o_limite_e_cobrado(client, cliente_id, produto_id):
    _movimento(client, produto_id, 3, 'aquisicao')
    _pedido_aprovado(client, cliente_id, produto_id, 2, JANELA_ITEM)

    retrato = _estoque(client, produto_id, **PERIODO).get_json()
    assert retrato['locado'] == 2
    assert retrato['disponivel'] == 1

    pedido = _post(client, '/api/pedidos', {'cliente_id': cliente_id}).get_json()
    recusa = _post(client, f"/api/pedidos/{pedido['id']}/itens",
                   {'produto_id': produto_id, 'quantidade': 2, **JANELA_ITEM})

    # 409: o pedido e valido e o produto existe -- o que nao serve e o
    # estado do estoque no periodo pedido.
    assert recusa.status_code == 409
    assert 'POLT-001' in recusa.get_json()['erro']
    assert '2' in recusa.get_json()['erro']


def test_quantidade_dentro_do_limite_passa(client, cliente_id, produto_id):
    _movimento(client, produto_id, 3, 'aquisicao')
    _pedido_aprovado(client, cliente_id, produto_id, 2, JANELA_ITEM)

    pedido = _post(client, '/api/pedidos', {'cliente_id': cliente_id}).get_json()
    assert _post(client, f"/api/pedidos/{pedido['id']}/itens",
                 {'produto_id': produto_id, 'quantidade': 1, **JANELA_ITEM}).status_code == 201


def test_janela_disjunta_nao_disputa_o_mesmo_equipamento(client, cliente_id, produto_id):
    _movimento(client, produto_id, 3, 'aquisicao')
    _pedido_aprovado(client, cliente_id, produto_id, 3, JANELA_ITEM)

    pedido = _post(client, '/api/pedidos', {'cliente_id': cliente_id}).get_json()
    # Junho e janeiro nao se tocam: as mesmas 3 poltronas estao livres.
    assert _post(client, f"/api/pedidos/{pedido['id']}/itens",
                 {'produto_id': produto_id, 'quantidade': 3,
                  **OUTRA_JANELA_ITEM}).status_code == 201


def test_aberto_nao_reserva_mas_aparece_como_negociacao(client, cliente_id, produto_id):
    _movimento(client, produto_id, 3, 'aquisicao')

    pedido = _post(client, '/api/pedidos', {'cliente_id': cliente_id}).get_json()
    _post(client, f"/api/pedidos/{pedido['id']}/itens",
          {'produto_id': produto_id, 'quantidade': 2, **JANELA_ITEM})
    _post(client, f"/api/pedidos/{pedido['id']}/abertura")

    retrato = _estoque(client, produto_id, **PERIODO).get_json()
    assert retrato['locado'] == 0
    assert retrato['em_negociacao'] == 2
    assert retrato['disponivel'] == 3

    # ... e outro pedido pode lancar item no mesmo produto e periodo:
    # proposta nao e compromisso.
    outro = _post(client, '/api/pedidos', {'cliente_id': cliente_id}).get_json()
    assert _post(client, f"/api/pedidos/{outro['id']}/itens",
                 {'produto_id': produto_id, 'quantidade': 3,
                  **JANELA_ITEM}).status_code == 201


def test_cancelar_o_pedido_devolve_a_reserva(client, cliente_id, produto_id):
    _movimento(client, produto_id, 3, 'aquisicao')
    pedido = _pedido_aprovado(client, cliente_id, produto_id, 3, JANELA_ITEM)

    _post(client, f"/api/pedidos/{pedido}/cancelamento", {'motivo': 'Cliente desistiu'})

    retrato = _estoque(client, produto_id, **PERIODO).get_json()
    assert retrato['locado'] == 0
    assert retrato['disponivel'] == 3


def test_item_sem_janela_ocupa_qualquer_periodo_consultado(client, cliente_id, produto_id):
    """
    Sem datas o sistema nao sabe devolver -- conservador e a unica resposta
    honesta. O retrato precisa DIZER que ha reserva sem janela, e nao
    apenas esconder dentro do total.
    """
    _movimento(client, produto_id, 3, 'aquisicao')

    pedido = _post(client, '/api/pedidos', {'cliente_id': cliente_id}).get_json()
    _post(client, f"/api/pedidos/{pedido['id']}/itens",
          {'produto_id': produto_id, 'quantidade': 2})
    _post(client, f"/api/pedidos/{pedido['id']}/abertura")
    _post(client, f"/api/pedidos/{pedido['id']}/aprovacao")

    retrato = _estoque(client, produto_id, **OUTRO_PERIODO).get_json()
    assert retrato['locado'] == 2
    assert retrato['sem_janela'] == 2
    assert retrato['disponivel'] == 1


def test_disponivel_negativo_aparece_como_esta(client, cliente_id, produto_id):
    """
    O razao desatualizado (mais locado do que existia no papel) e o alerta
    mais importante do controle. max(0, ...) o transformaria em silencio.
    """
    _movimento(client, produto_id, 1, 'aquisicao')
    _pedido_aprovado(client, cliente_id, produto_id, 1, JANELA_ITEM)
    _movimento(client, produto_id, -1, 'baixa', 'A poltrona quebrou')

    retrato = _estoque(client, produto_id, **PERIODO).get_json()
    assert retrato['disponivel'] == -1


# =============================================================================
# A borda HTTP
# =============================================================================
def test_periodo_meio_e_recusado(client, produto_id):
    _movimento(client, produto_id, 1, 'aquisicao')

    so_inicio = _estoque(client, produto_id, inicio='2030-01-01')
    assert so_inicio.status_code == 400
    assert 'inicio e fim' in so_inicio.get_json()['erro']

    ordem_trocada = _estoque(client, produto_id, inicio='2030-02-01',
                            fim='2030-01-01')
    assert ordem_trocada.status_code == 400


def test_resumo_cobre_todos_os_produtos_ativos(client, produto_id):
    _movimento(client, produto_id, 2, 'aquisicao')
    outro = _post(client, '/api/produtos', {
        'codigo': 'POLT-002', 'descricao': 'Poltrona Ghost', 'preco_venda': '10,00'
    }).get_json()['id']

    resumo = client.get('/api/estoque/resumo').get_json()

    por_id = {r['produto_id']: r for r in resumo}
    assert por_id[produto_id]['total'] == 2
    assert por_id[produto_id]['disponivel'] == 2
    # Sem razao: catalogo puro, marcado como tal.
    assert por_id[outro]['configurado'] is False
