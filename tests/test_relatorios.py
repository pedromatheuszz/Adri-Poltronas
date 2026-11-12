"""
Relatorio financeiro: as parcelas reunidas, com resumo que fecha.

O defeito que este modulo existe para impedir e o resumo que diverge da
tabela: dois SELECTs independentes, um para as linhas e outro para os
totais, que concordam na demo e divergem no primeiro filtro composto. Aqui
o resumo e calculado sobre as MESMAS linhas devolvidas -- e o teste
exercita isso com filtros que um resumo ingenuo pega errado.
"""
import io
import json
import os
import sys
import tempfile

import openpyxl
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


def _post(client, rota, corpo=None):
    return client.post(rota, headers=CABECALHOS, data=json.dumps(corpo or {}))


@pytest.fixture
def cliente_id():
    return database.salvar_cliente(
        'Dona Marta', '89200-000', 'Rua A, 10', 'Centro', 'Joinville', 'Entrega')


@pytest.fixture
def tres_clientes():
    """
    Tres clientes reais para os cenarios que semeiam parcelas de varias
    pessoas. A FK de `pagamentos.cliente_id` e enforcement de verdade
    (`PRAGMA foreign_keys = ON`), e semear linha apontando para cliente
    inexistente e montar cenario com dado que o banco inteiro recusaria.
    """
    return [
        database.salvar_cliente(
            f'Cliente {i}', '89200-000', 'Rua A', 'Centro', 'Joinville', 'Entrega')
        for i in (1, 2, 3)
    ]


def _pedido_faturado(client, cliente_id, produto_id):
    """Fluxo inteiro ate as parcelas existirem: e elas que o relatorio le."""
    pedido = _post(client, '/api/pedidos', {'cliente_id': cliente_id}).get_json()
    _post(client, f"/api/pedidos/{pedido['id']}/itens",
          {'produto_id': produto_id, 'quantidade': 1, 'preco_unitario': '120,50'})
    _post(client, f"/api/pedidos/{pedido['id']}/abertura")
    _post(client, f"/api/pedidos/{pedido['id']}/aprovacao")
    _post(client, f"/api/pedidos/{pedido['id']}/faturamento",
          {'parcelas': 2, 'primeiro_vencimento': '2030-01-10',
           'forma_pagamento': 'Pix'})
    return pedido['id']


def _relatorio(client, **params):
    query = '&'.join(f'{k}={v}' for k, v in params.items())
    return client.get('/api/relatorios/financeiro' +
                      (f'?{query}' if query else ''))


# =============================================================================
# A tabela
# =============================================================================
def test_relatorio_vazio_tem_resumo_zero_e_lista_vazia(client):
    resposta = _relatorio(client)

    assert resposta.status_code == 200
    dados = resposta.get_json()
    assert dados['parcelas'] == []
    assert dados['resumo']['quantidade'] == 0
    assert dados['resumo']['a_receber']['centavos'] == 0


def test_parcela_de_pedido_aparece_com_numero_do_pedido(client, cliente_id, semear_parcela):
    produto = _post(client, '/api/produtos', {
        'codigo': 'P1', 'descricao': 'Poltrona', 'preco_venda': '10,00'}).get_json()
    _pedido_faturado(client, cliente_id, produto['id'])
    # A orfa de versao anterior: dinheiro real sem pedido de origem.
    semear_parcela(cliente_id, cliente_nome='Dona Marta')

    parcelas = _relatorio(client).get_json()['parcelas']

    com_pedido = [p for p in parcelas if p['pedido_id']]
    assert len(com_pedido) == 2  # o faturamento de 2x
    assert all(p['pedido_numero'].startswith('PED-') for p in com_pedido)

    orfa = [p for p in parcelas if not p['pedido_id']]
    assert len(orfa) == 1
    assert not orfa[0]['pedido_numero']


def test_o_atraso_e_derivado_do_vencimento_nao_do_que_foi_gravado(client, tres_clientes, semear_parcela):
    semear_parcela(tres_clientes[0], data_vencimento='2020-01-01')  # venceu ha tempo
    semear_parcela(tres_clientes[1], data_vencimento='2030-01-01')  # ainda nao venceu

    parcelas = {p['cliente_id']: p for p in _relatorio(client).get_json()['parcelas']}

    vencida = parcelas[tres_clientes[0]]
    a_vencer = parcelas[tres_clientes[1]]
    assert vencida['status'] == 'Pendente'
    assert vencida['em_atraso'] is True
    assert a_vencer['em_atraso'] is False


# =============================================================================
# Os filtros
# =============================================================================
def test_filtro_de_situacao_separa_as_parcelas(client, tres_clientes, semear_parcela):
    semear_parcela(tres_clientes[0], status='Pendente')
    semear_parcela(tres_clientes[1], status='Recebido')
    semear_parcela(tres_clientes[2], status='Cancelado')

    pendentes = _relatorio(client, situacao='Pendente').get_json()['parcelas']
    assert [p['cliente_id'] for p in pendentes] == [tres_clientes[0]]

    recebidas = _relatorio(client, situacao='Recebido').get_json()['parcelas']
    assert [p['cliente_id'] for p in recebidas] == [tres_clientes[1]]


def test_filtro_atrasadas_e_o_calendario_que_responde(client, tres_clientes, semear_parcela):
    semear_parcela(tres_clientes[0], data_vencimento='2020-01-01')
    semear_parcela(tres_clientes[1], data_vencimento='2030-01-01')

    atrasadas = _relatorio(client, situacao='atrasadas').get_json()['parcelas']

    assert [p['cliente_id'] for p in atrasadas] == [tres_clientes[0]]


def test_filtro_de_vencimento_pega_o_periodo_fechado(client, tres_clientes, semear_parcela):
    semear_parcela(tres_clientes[0], data_vencimento='2030-01-05')
    semear_parcela(tres_clientes[1], data_vencimento='2030-02-05')

    janeiro = _relatorio(client, de='2030-01-01', ate='2030-01-31')
    ids = [p['cliente_id'] for p in janeiro.get_json()['parcelas']]
    assert ids == [tres_clientes[0]]

    # Data unica: o dia inteiro, e nao "a partir da meia-noite".
    so_um_dia = _relatorio(client, de='2030-02-05')
    ids = [p['cliente_id'] for p in so_um_dia.get_json()['parcelas']]
    assert ids == [tres_clientes[1]]


@pytest.mark.parametrize('params, fragmento', [
    ({'ate': '2030-01-01'}, 'inicial'),
    ({'de': '2030-02-01', 'ate': '2030-01-01'}, 'antes da inicial'),
    ({'de': '2030-13-01'}, 'invalida'),
    ({'situacao': 'perdida'}, 'Situacao invalida'),
])
def test_filtro_impossivel_e_400_com_mensagem_util(client, params, fragmento):
    resposta = _relatorio(client, **params)
    assert resposta.status_code == 400
    assert fragmento in resposta.get_json()['erro']


# =============================================================================
# O resumo fecha com a tabela, sempre
# =============================================================================
def test_o_resumo_e_calculado_sobre_as_linhas_filtradas(client, tres_clientes, semear_parcela):
    """
    Duas pendentes (uma atrasada) e uma recebida. O resumo do filtro
    `Pendente` precisa contar as duas -- a atrasada continua sendo dinheiro
    a receber, e a caixa "atrasado" e detalhe da caixa "a receber", nao uma
    terceira especie de parcela.
    """
    semear_parcela(tres_clientes[0], data_vencimento='2020-01-01', valor_centavos=10000)
    semear_parcela(tres_clientes[1], data_vencimento='2030-01-01', valor_centavos=25000)
    semear_parcela(tres_clientes[2], status='Recebido', valor_centavos=50000)

    dados = _relatorio(client, situacao='Pendente').get_json()

    assert dados['resumo']['quantidade'] == 2
    assert dados['resumo']['a_receber']['centavos'] == 35000
    assert dados['resumo']['atrasado']['centavos'] == 10000
    assert dados['resumo']['recebido']['centavos'] == 0

    # E o total sem filtro tambem fecha com a soma da propria tabela.
    tudo = _relatorio(client).get_json()
    soma = sum(p['valor_centavos'] for p in tudo['parcelas'])
    assert (tudo['resumo']['a_receber']['centavos']
            + tudo['resumo']['recebido']['centavos']) == soma


# =============================================================================
# A exportacao
# =============================================================================
def test_exportacao_entrega_xlsx_com_as_mesmas_linhas(client, tres_clientes, semear_parcela):
    semear_parcela(tres_clientes[0], cliente_nome='"Marta" & Cia',
                   data_vencimento='2020-01-01')

    resposta = client.get('/api/relatorios/financeiro/exportar?situacao=Pendente')

    assert resposta.status_code == 200
    assert 'spreadsheetml' in resposta.headers['Content-Type']
    assert resposta.headers['Content-Disposition'].index('relatorio_parcelas_')

    planilha = openpyxl.load_workbook(io.BytesIO(resposta.data))
    aba = planilha.active
    # Cabecalho + 1 linha; o valor sai como texto formatado, nao numero.
    assert aba.max_row == 2
    assert aba.cell(row=2, column=1).value == '2020-01-01'
    assert aba.cell(row=2, column=5).value == 'R$ 120,50'


def test_exportacao_valida_o_mesmo_filtro_da_tela(client):
    resposta = client.get('/api/relatorios/financeiro/exportar?situacao=perdida')
    assert resposta.status_code == 400
