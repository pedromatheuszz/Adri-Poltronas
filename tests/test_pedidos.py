"""
Catalogo de produtos e pedido de venda.

Ate este modulo o sistema nao registrava O QUE foi vendido: pagamentos e
entregas ficavam pendurados direto no cliente. O pedido e a espinha que liga
as duas coisas -- e o faturamento, que emite as parcelas a receber, e o ponto
onde um erro custa dinheiro.
"""
import datetime
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


def _post(cliente, rota, corpo=None):
    return cliente.post(rota, headers=CABECALHOS, data=json.dumps(corpo or {}))


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


def _pedido_com_item(client, cliente_id, produto_id, **cabecalho):
    pedido = _post(client, '/api/pedidos', {'cliente_id': cliente_id, **cabecalho}).get_json()
    _post(client, f"/api/pedidos/{pedido['id']}/itens",
          {'produto_id': produto_id, 'quantidade': 1})
    return pedido['id']


# =============================================================================
# Catalogo
# =============================================================================
def test_produto_guarda_preco_em_centavos(client):
    resposta = _post(client, '/api/produtos', {
        'codigo': 'P1', 'descricao': 'Poltrona', 'preco_venda': '1.850,00'})

    assert resposta.status_code == 201
    dados = resposta.get_json()
    assert dados['preco_venda_centavos'] == 185000
    # A tela recebe o formatado pronto para nao reimplementar moeda.
    assert dados['preco_venda']['formatado'] == 'R$ 1.850,00'


def test_codigo_duplicado_entre_ativos_e_recusado(client, produto_id):
    resposta = _post(client, '/api/produtos', {'codigo': 'POLT-001', 'descricao': 'Outra'})
    assert resposta.status_code == 400
    assert 'codigo' in resposta.get_json()['erro'].lower()


def test_codigo_volta_a_ficar_livre_apos_inativar(client, produto_id):
    """O indice unico e parcial: so vale entre os ativos."""
    client.delete(f'/api/produtos/{produto_id}', headers=CABECALHOS)
    assert _post(client, '/api/produtos',
                 {'codigo': 'POLT-001', 'descricao': 'Nova versao'}).status_code == 201


def test_produto_e_inativado_e_nao_apagado(client, produto_id):
    """Produto usado em pedido nao pode sumir -- o pedido perderia a referencia."""
    client.delete(f'/api/produtos/{produto_id}', headers=CABECALHOS)

    assert client.get('/api/produtos').get_json() == []
    assert len(client.get('/api/produtos?incluir_inativos=1').get_json()) == 1


@pytest.mark.parametrize('invalido, motivo', [
    ({'descricao': 'Sem codigo'}, 'codigo'),
    ({'codigo': 'X'}, 'descricao'),
    ({'codigo': 'X', 'descricao': 'Y', 'unidade': 'xyz'}, 'unidade'),
    ({'codigo': 'X', 'descricao': 'Y', 'preco_venda': 'abc'}, 'monetario'),
])
def test_produto_invalido_e_recusado(client, invalido, motivo):
    resposta = _post(client, '/api/produtos', invalido)
    assert resposta.status_code == 400
    assert motivo in resposta.get_json()['erro'].lower()


# =============================================================================
# Pedido: cabecalho e itens
# =============================================================================
def test_pedido_nasce_em_rascunho_com_numero_sequencial(client, cliente_id):
    primeiro = _post(client, '/api/pedidos', {'cliente_id': cliente_id}).get_json()
    segundo = _post(client, '/api/pedidos', {'cliente_id': cliente_id}).get_json()

    assert primeiro['situacao'] == 'rascunho'
    assert primeiro['numero'].endswith('000001')
    assert segundo['numero'].endswith('000002')


def test_pedido_guarda_o_prazo_da_encomenda(client, cliente_id):
    """Fabricacao sob encomenda: sem prazo o pedido nao serve para nada."""
    pedido = _post(client, '/api/pedidos', {
        'cliente_id': cliente_id, 'data_entrega_prevista': '2026-12-24'}).get_json()
    assert pedido['data_entrega_prevista'] == '2026-12-24'


def test_pedido_para_cliente_inexistente_e_recusado(client):
    assert _post(client, '/api/pedidos', {'cliente_id': 99999}).status_code == 404


def test_item_herda_descricao_do_catalogo(client, cliente_id, produto_id):
    pedido = _post(client, '/api/pedidos', {'cliente_id': cliente_id}).get_json()
    resposta = _post(client, f"/api/pedidos/{pedido['id']}/itens",
                     {'produto_id': produto_id, 'quantidade': 1})

    assert resposta.get_json()['itens'][0]['descricao'] == 'Poltrona Costela'


def test_item_aceita_descricao_propria(client, cliente_id, produto_id):
    """Cada poltrona tem tecido, acabamento e medida proprios."""
    pedido = _post(client, '/api/pedidos', {'cliente_id': cliente_id}).get_json()
    resposta = _post(client, f"/api/pedidos/{pedido['id']}/itens", {
        'produto_id': produto_id, 'quantidade': 1,
        'descricao': 'Poltrona Costela - linho cru, pes nogueira'})

    assert 'linho cru' in resposta.get_json()['itens'][0]['descricao']


def test_totais_somam_itens_menos_desconto_mais_frete(client, cliente_id, produto_id):
    pedido = _post(client, '/api/pedidos', {
        'cliente_id': cliente_id, 'desconto': '50,00', 'frete': '150,00'}).get_json()
    resposta = _post(client, f"/api/pedidos/{pedido['id']}/itens",
                     {'produto_id': produto_id, 'quantidade': 2})

    dados = resposta.get_json()
    assert dados['total_bruto_centavos'] == 370000          # 2 x 1.850,00
    assert dados['total_liquido_centavos'] == 370000 - 5000 + 15000


def test_desconto_maior_que_o_pedido_e_recusado(client, cliente_id, produto_id):
    pedido_id = _pedido_com_item(client, cliente_id, produto_id)
    resposta = client.put(f'/api/pedidos/{pedido_id}', headers=CABECALHOS,
                          data=json.dumps({'cliente_id': cliente_id, 'desconto': '9.999,00'}))

    assert resposta.status_code == 400
    assert 'negativo' in resposta.get_json()['erro'].lower()


def test_preco_do_item_pode_ser_negociado(client, cliente_id, produto_id):
    """Encomenda negocia valor caso a caso; sem informar, cai no catalogo."""
    pedido = _post(client, '/api/pedidos', {'cliente_id': cliente_id}).get_json()
    resposta = _post(client, f"/api/pedidos/{pedido['id']}/itens",
                     {'produto_id': produto_id, 'quantidade': 1, 'preco_unitario': '1.500,00'})

    assert resposta.get_json()['total_liquido_centavos'] == 150000


def test_remover_item_recalcula_o_total(client, cliente_id, produto_id):
    pedido_id = _pedido_com_item(client, cliente_id, produto_id)
    item_id = client.get(f'/api/pedidos/{pedido_id}').get_json()['itens'][0]['id']

    resposta = client.delete(f'/api/pedidos/{pedido_id}/itens/{item_id}', headers=CABECALHOS)

    assert resposta.status_code == 200
    assert resposta.get_json()['total_liquido_centavos'] == 0


# =============================================================================
# Maquina de estados
# =============================================================================
def test_ciclo_completo(client, cliente_id, produto_id):
    pedido_id = _pedido_com_item(client, cliente_id, produto_id)

    assert _post(client, f'/api/pedidos/{pedido_id}/abertura').get_json()['situacao'] == 'aberto'
    assert _post(client, f'/api/pedidos/{pedido_id}/aprovacao').get_json()['situacao'] == 'aprovado'
    faturado = _post(client, f'/api/pedidos/{pedido_id}/faturamento',
                     {'parcelas': 1, 'primeiro_vencimento': '2026-10-05'})
    assert faturado.get_json()['situacao'] == 'faturado'


def test_pedido_sem_itens_nao_abre(client, cliente_id):
    pedido = _post(client, '/api/pedidos', {'cliente_id': cliente_id}).get_json()
    resposta = _post(client, f"/api/pedidos/{pedido['id']}/abertura")

    assert resposta.status_code == 400
    assert 'sem itens' in resposta.get_json()['erro'].lower()


def test_nao_da_para_pular_a_aprovacao(client, cliente_id, produto_id):
    """409, e nao 400: os dados sao validos -- o que nao serve e a situacao."""
    pedido_id = _pedido_com_item(client, cliente_id, produto_id)
    _post(client, f'/api/pedidos/{pedido_id}/abertura')

    resposta = _post(client, f'/api/pedidos/{pedido_id}/faturamento',
                     {'parcelas': 1, 'primeiro_vencimento': '2026-10-05'})
    assert resposta.status_code == 409


def test_pedido_cancelado_nao_fatura(client, cliente_id, produto_id):
    pedido_id = _pedido_com_item(client, cliente_id, produto_id)
    _post(client, f'/api/pedidos/{pedido_id}/cancelamento', {'motivo': 'Cliente desistiu'})

    resposta = _post(client, f'/api/pedidos/{pedido_id}/faturamento',
                     {'parcelas': 1, 'primeiro_vencimento': '2026-10-05'})
    assert resposta.status_code == 409


def test_faturar_duas_vezes_e_recusado(client, cliente_id, produto_id):
    """Sem isto, refaturar duplicaria as parcelas a receber."""
    pedido_id = _pedido_com_item(client, cliente_id, produto_id)
    _post(client, f'/api/pedidos/{pedido_id}/abertura')
    _post(client, f'/api/pedidos/{pedido_id}/aprovacao')
    corpo = {'parcelas': 1, 'primeiro_vencimento': '2026-10-05'}

    assert _post(client, f'/api/pedidos/{pedido_id}/faturamento', corpo).status_code == 200
    assert _post(client, f'/api/pedidos/{pedido_id}/faturamento', corpo).status_code == 409
    assert len(database.listar_pagamentos(cliente_id=cliente_id)) == 1


def test_item_nao_muda_apos_aprovacao(client, cliente_id, produto_id):
    pedido_id = _pedido_com_item(client, cliente_id, produto_id)
    _post(client, f'/api/pedidos/{pedido_id}/abertura')
    _post(client, f'/api/pedidos/{pedido_id}/aprovacao')

    resposta = _post(client, f'/api/pedidos/{pedido_id}/itens',
                     {'produto_id': produto_id, 'quantidade': 1})
    assert resposta.status_code == 409


def test_pedido_informa_os_proximos_passos_para_a_tela(client, cliente_id, produto_id):
    """A tela decide os botoes por isto, em vez de repetir a regra em JS."""
    pedido_id = _pedido_com_item(client, cliente_id, produto_id)
    pedido = client.get(f'/api/pedidos/{pedido_id}').get_json()

    assert pedido['proximos_passos'] == ['aberto', 'cancelado']
    assert pedido['editavel'] is True
    assert pedido['aceita_entrega'] is False


# =============================================================================
# Faturamento: onde o dinheiro acontece
# =============================================================================
def _faturar(client, cliente_id, produto_id, quantidade=1, **faturamento):
    pedido = _post(client, '/api/pedidos', {'cliente_id': cliente_id}).get_json()
    _post(client, f"/api/pedidos/{pedido['id']}/itens",
          {'produto_id': produto_id, 'quantidade': quantidade})
    _post(client, f"/api/pedidos/{pedido['id']}/abertura")
    _post(client, f"/api/pedidos/{pedido['id']}/aprovacao")
    corpo = {'parcelas': 1, 'primeiro_vencimento': '2026-10-05', **faturamento}
    return _post(client, f"/api/pedidos/{pedido['id']}/faturamento", corpo)


def test_faturamento_emite_uma_parcela_por_vez(client, cliente_id, produto_id):
    parcelas = _faturar(client, cliente_id, produto_id, parcelas=3).get_json()['parcelas']

    assert [p['parcela'] for p in parcelas] == [1, 2, 3]
    assert all(p['total_parcelas'] == 3 for p in parcelas)
    assert all(p['status'] == 'Pendente' for p in parcelas)


def test_soma_das_parcelas_e_exatamente_o_total(client, cliente_id, produto_id):
    """
    O ponto mais caro do modulo. 1.850,00 em 3 nao divide exato: sem rateio
    explicito, o cliente e cobrado a mais ou a menos que o pedido.
    """
    resposta = _faturar(client, cliente_id, produto_id, parcelas=3).get_json()
    # Somado em CENTAVOS, nunca a partir do `valor` REAL: e exatamente a
    # conversao para float que desfazia o rateio exato, e somar o float aqui
    # tornaria o teste cumplice do defeito que ele existe para pegar.
    soma_centavos = sum(p['valor']['centavos'] for p in resposta['parcelas'])

    assert soma_centavos == resposta['total_liquido_centavos'] == 185000


def test_vencimentos_sao_mensais_a_partir_do_primeiro(client, cliente_id, produto_id):
    parcelas = _faturar(client, cliente_id, produto_id, parcelas=3,
                        primeiro_vencimento='2026-10-05').get_json()['parcelas']

    assert [p['data_vencimento'] for p in parcelas] == ['2026-10-05', '2026-11-05', '2026-12-05']


def test_vencimento_no_dia_31_cai_para_o_fim_do_mes_curto(client, cliente_id, produto_id):
    """Parcelamento comecando em 31/01 nao pode estourar em fevereiro."""
    parcelas = _faturar(client, cliente_id, produto_id, parcelas=3,
                        primeiro_vencimento='2026-01-31').get_json()['parcelas']

    assert [p['data_vencimento'] for p in parcelas] == ['2026-01-31', '2026-02-28', '2026-03-31']




def test_parcela_referencia_o_pedido_de_origem(client, cliente_id, produto_id):
    resposta = _faturar(client, cliente_id, produto_id, parcelas=1).get_json()

    parcela = database.listar_pagamentos(cliente_id=cliente_id)[0]
    assert parcela['pedido_id'] == resposta['id']
    assert resposta['numero'] in parcela['descricao']


@pytest.mark.parametrize('invalido, esperado', [
    ({'primeiro_vencimento': 'nao-e-data'}, 'vencimento'),
    ({'parcelas': 99}, 'parcelas'),
    ({'forma_pagamento': 'Bitcoin'}, 'forma de pagamento'),
])
def test_faturamento_invalido_e_recusado(client, cliente_id, produto_id, invalido, esperado):
    resposta = _faturar(client, cliente_id, produto_id, **invalido)
    assert resposta.status_code == 400
    assert esperado in resposta.get_json()['erro'].lower()


# =============================================================================
# Recebiveis: o outro lado do faturamento
# =============================================================================
# Ate a 1.5.0 esta secao nao podia existir. O faturamento emitia as parcelas, a
# aba que as mostrava foi removida junto com o Asaas, e o pedido virava terminal
# -- entao o dinheiro ficava registrado a receber sem lugar nenhum no aplicativo
# para ver, conferir ou dar baixa. O ciclo order-to-cash nao fechava.
def _patch(cliente, rota, corpo=None):
    return cliente.patch(rota, headers=CABECALHOS, data=json.dumps(corpo or {}))


def test_o_pedido_devolve_as_parcelas_que_emitiu(client, cliente_id, produto_id):
    """A tela le as parcelas daqui: e o unico lugar que as expoe."""
    pedido_id = _faturar(client, cliente_id, produto_id, parcelas=3).get_json()['id']

    pedido = client.get(f'/api/pedidos/{pedido_id}').get_json()

    assert len(pedido['parcelas']) == 3
    assert all(p['status'] == 'Pendente' for p in pedido['parcelas'])
    # `valor` chega no formato canonico da API, com centavos E texto: sem os
    # centavos a tela refaz parsing de moeda, sem o texto cada tela reimplementa
    # a formatacao e elas divergem.
    assert pedido['parcelas'][0]['valor']['centavos'] > 0
    assert pedido['parcelas'][0]['valor']['formatado'].startswith('R$')


def test_dar_baixa_marca_a_parcela_como_recebida(client, cliente_id, produto_id):
    pedido_id = _faturar(client, cliente_id, produto_id, parcelas=2).get_json()['id']

    resposta = _patch(client, f'/api/pedidos/{pedido_id}/parcelas/1',
                      {'status': 'Recebido', 'data_pagamento': '2026-10-06'})

    assert resposta.status_code == 200
    assert resposta.get_json()['status'] == 'Recebido'
    assert resposta.get_json()['data_pagamento'] == '2026-10-06'

    parcelas = client.get(f'/api/pedidos/{pedido_id}').get_json()['parcelas']
    assert [p['status'] for p in parcelas] == ['Recebido', 'Pendente']


def test_baixa_sem_data_usa_hoje(client, cliente_id, produto_id):
    """
    O caso esmagadoramente mais comum e marcar no momento em que se recebe.
    Exigir a data acrescentaria um clique a operacao mais frequente.
    """
    pedido_id = _faturar(client, cliente_id, produto_id).get_json()['id']

    recebida = _patch(client, f'/api/pedidos/{pedido_id}/parcelas/1',
                      {'status': 'Recebido'}).get_json()

    assert recebida['data_pagamento'] == datetime.date.today().isoformat()


def test_desfazer_a_baixa_limpa_a_data_de_pagamento(client, cliente_id, produto_id):
    """
    Uma parcela 'Pendente' com data de pagamento preenchida e a contradicao que
    faz relatorio mentir: ela aparece em aberto e como recebida ao mesmo tempo.
    """
    pedido_id = _faturar(client, cliente_id, produto_id).get_json()['id']
    _patch(client, f'/api/pedidos/{pedido_id}/parcelas/1', {'status': 'Recebido'})

    voltou = _patch(client, f'/api/pedidos/{pedido_id}/parcelas/1',
                    {'status': 'Pendente'}).get_json()

    assert voltou['status'] == 'Pendente'
    assert voltou['data_pagamento'] == ''


def test_baixa_repetida_e_recusada_com_409(client, cliente_id, produto_id):
    """Dois cliques em 'Receber' nao podem gravar dois eventos de auditoria."""
    pedido_id = _faturar(client, cliente_id, produto_id).get_json()['id']
    assert _patch(client, f'/api/pedidos/{pedido_id}/parcelas/1',
                  {'status': 'Recebido'}).status_code == 200
    assert _patch(client, f'/api/pedidos/{pedido_id}/parcelas/1',
                  {'status': 'Recebido'}).status_code == 409


def test_atraso_e_derivado_do_vencimento_e_nao_gravado(client, cliente_id, produto_id):
    """
    'Atrasado' nao e status declarado: seria preciso uma rotina passando
    meia-noite para reescrever linhas, e ate ela rodar a tela mentiria. O status
    gravado diz o que o operador declarou; `em_atraso` diz o que o calendario diz.
    """
    pedido_id = _faturar(client, cliente_id, produto_id,
                         primeiro_vencimento='2020-01-10').get_json()['id']

    parcela = client.get(f'/api/pedidos/{pedido_id}').get_json()['parcelas'][0]

    assert parcela['status'] == 'Pendente'
    assert parcela['em_atraso'] is True

    # Recebida deixa de estar em atraso, mesmo com o vencimento no passado.
    _patch(client, f'/api/pedidos/{pedido_id}/parcelas/1', {'status': 'Recebido'})
    parcela = client.get(f'/api/pedidos/{pedido_id}').get_json()['parcelas'][0]
    assert parcela['em_atraso'] is False


@pytest.mark.parametrize('corpo, status', [
    ({'status': 'Atrasado'}, 400),   # derivado, nao declaravel
    ({'status': 'Bitcoin'}, 400),
    ({}, 400),
    ({'status': 'Recebido', 'data_pagamento': '2026-13-45'}, 400),
])
def test_baixa_invalida_e_recusada(client, cliente_id, produto_id, corpo, status):
    pedido_id = _faturar(client, cliente_id, produto_id).get_json()['id']
    assert _patch(client, f'/api/pedidos/{pedido_id}/parcelas/1', corpo).status_code == status


def test_baixa_em_parcela_inexistente_e_404(client, cliente_id, produto_id):
    pedido_id = _faturar(client, cliente_id, produto_id).get_json()['id']
    assert _patch(client, f'/api/pedidos/{pedido_id}/parcelas/9',
                  {'status': 'Recebido'}).status_code == 404




# =============================================================================
# Regressao: DEFAULT de texto vazio (migration d1e7b3f5620a)
# =============================================================================
