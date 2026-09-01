"""Testes da API HTTP /api/v2: contrato, status e formato."""
from __future__ import annotations

import json


def post(cliente, rota, corpo=None):
    return cliente.post(rota, data=json.dumps(corpo or {}), content_type='application/json')


def put(cliente, rota, corpo=None):
    return cliente.put(rota, data=json.dumps(corpo or {}), content_type='application/json')


def corpo_de(resposta):
    return json.loads(resposta.data)


# ---------------------------------------------------------------------------
# Contrato geral
# ---------------------------------------------------------------------------
def test_saude_responde_com_a_versao(cliente_http):
    resposta = cliente_http.get('/api/v2/saude')
    assert resposta.status_code == 200
    assert corpo_de(resposta)['versao_api'] == '2.0.0'


def test_rota_inexistente_devolve_json_e_nao_html(cliente_http):
    resposta = cliente_http.get('/api/v2/nao-existe')
    assert resposta.status_code == 404
    assert resposta.mimetype == 'application/json'
    assert 'erro' in corpo_de(resposta)


def test_recurso_inexistente_devolve_404_com_codigo(cliente_http):
    resposta = cliente_http.get('/api/v2/parceiros/99999')
    assert resposta.status_code == 404
    assert corpo_de(resposta)['codigo'] == 'nao_encontrado'


def test_validacao_devolve_400_com_a_lista_de_erros(cliente_http):
    resposta = post(cliente_http, '/api/v2/parceiros', {'nome': ''})
    assert resposta.status_code == 400
    corpo = corpo_de(resposta)
    assert corpo['codigo'] == 'dados_invalidos'
    assert isinstance(corpo['detalhes'], list) and corpo['detalhes']


def test_correlation_id_volta_no_cabecalho(cliente_http):
    resposta = cliente_http.get('/api/v2/saude')
    assert resposta.headers.get('X-Correlation-ID')


def test_correlation_id_limpo_e_aceito(cliente_http):
    resposta = cliente_http.get('/api/v2/saude',
                                headers={'X-Correlation-ID': 'abc-123_XYZ.4:5'})
    assert resposta.headers['X-Correlation-ID'] == 'abc-123_XYZ.4:5'


def test_correlation_id_suspeito_e_substituido(cliente_http):
    """
    O cabecalho vai para o log e para a trilha de auditoria, entao nao entra
    cru. (Newline nao da para testar aqui: o werkzeug recusa montar o header
    antes de a requisicao chegar ao app -- por isso os casos abaixo usam
    caracteres validos em HTTP, porem fora da allowlist.)
    """
    for suspeito in ('id com espaco', '<script>alert(1)</script>', 'x' * 200, ';drop'):
        resposta = cliente_http.get('/api/v2/saude',
                                    headers={'X-Correlation-ID': suspeito})
        devolvido = resposta.headers['X-Correlation-ID']
        assert devolvido != suspeito, suspeito
        assert len(devolvido) == 32 and devolvido.isalnum()


def test_cabecalhos_de_seguranca(cliente_http):
    resposta = cliente_http.get('/api/v2/saude')
    assert resposta.headers['X-Content-Type-Options'] == 'nosniff'
    assert resposta.headers['X-Frame-Options'] == 'DENY'


# ---------------------------------------------------------------------------
# Dinheiro na saida
# ---------------------------------------------------------------------------
def test_resposta_traz_inteiro_e_texto_do_valor(cliente_http):
    resposta = post(cliente_http, '/api/v2/produtos', {
        'codigo': 'X1', 'descricao': 'Produto de teste', 'preco_venda': '1.234,56',
    })
    assert resposta.status_code == 201
    corpo = corpo_de(resposta)
    # O inteiro para calcular, o texto para exibir -- os dois na mesma resposta.
    assert corpo['preco_venda_centavos'] == 123456
    assert corpo['preco_venda'] == 'R$ 1.234,56'


# ---------------------------------------------------------------------------
# Paginacao
# ---------------------------------------------------------------------------
def test_listagem_e_sempre_paginada(cliente_http, dados_base):
    resposta = cliente_http.get('/api/v2/parceiros')
    corpo = corpo_de(resposta)
    assert 'itens' in corpo and 'paginacao' in corpo
    assert corpo['paginacao']['total'] == 2
    assert corpo['paginacao']['tem_proxima'] is False


def test_limite_da_pagina_tem_teto(cliente_http, dados_base):
    corpo = corpo_de(cliente_http.get('/api/v2/parceiros?limite=99999'))
    assert corpo['paginacao']['limite'] == 200


def test_filtro_por_papel(cliente_http, dados_base):
    clientes = corpo_de(cliente_http.get('/api/v2/parceiros?papel=cliente'))
    fornecedores = corpo_de(cliente_http.get('/api/v2/parceiros?papel=fornecedor'))
    assert clientes['paginacao']['total'] == 1
    assert fornecedores['paginacao']['total'] == 1


# ---------------------------------------------------------------------------
# Fluxo completo pela API
# ---------------------------------------------------------------------------
def test_ciclo_comercial_completo_via_http(cliente_http):
    fornecedor = corpo_de(post(cliente_http, '/api/v2/parceiros', {
        'nome': 'Fornecedor SA', 'documento': '11.222.333/0001-81',
        'e_cliente': False, 'e_fornecedor': True}))
    cliente = corpo_de(post(cliente_http, '/api/v2/parceiros', {
        'nome': 'Cliente Final', 'documento': '529.982.247-25'}))
    produto = corpo_de(post(cliente_http, '/api/v2/produtos', {
        'codigo': 'PLT-9', 'descricao': 'Poltrona', 'preco_venda': '1.000,00'}))
    conta = corpo_de(post(cliente_http, '/api/v2/financeiro/contas', {
        'nome': 'Caixa', 'saldo_inicial': '0,00'}))

    # Compra -> recebimento
    compra = corpo_de(post(cliente_http, '/api/v2/compras', {
        'parceiro_id': fornecedor['id'],
        'itens': [{'produto_id': produto['id'], 'quantidade': 4,
                   'preco_unitario': '600,00'}]}))
    assert post(cliente_http, '/api/v2/compras/%d/abertura' % compra['id']).status_code == 200
    recebida = corpo_de(post(cliente_http, '/api/v2/compras/%d/recebimento' % compra['id'],
                             {'parcelas': 1, 'primeiro_vencimento': '2030-01-10'}))
    assert recebida['situacao'] == 'recebido'

    saldo = corpo_de(cliente_http.get('/api/v2/estoque/saldos/%d' % produto['id']))
    assert saldo['saldo'] == 4

    # Venda -> faturamento
    venda = corpo_de(post(cliente_http, '/api/v2/vendas', {
        'parceiro_id': cliente['id'],
        'itens': [{'produto_id': produto['id'], 'quantidade': 2}]}))
    post(cliente_http, '/api/v2/vendas/%d/abertura' % venda['id'])
    post(cliente_http, '/api/v2/vendas/%d/aprovacao' % venda['id'])
    faturada = corpo_de(post(cliente_http, '/api/v2/vendas/%d/faturamento' % venda['id'],
                             {'parcelas': 2, 'primeiro_vencimento': '2030-02-10'}))
    assert faturada['situacao'] == 'faturado'
    assert corpo_de(cliente_http.get('/api/v2/estoque/saldos/%d' % produto['id']))['saldo'] == 2

    # Baixa
    titulos = corpo_de(cliente_http.get('/api/v2/financeiro/titulos?natureza=receber'))
    primeiro = titulos['itens'][0]
    baixado = corpo_de(post(
        cliente_http,
        '/api/v2/financeiro/titulos/%d/baixas' % primeiro['titulo_id'],
        {'conta_id': conta['id'], 'valor_centavos': primeiro['saldo_centavos']}))
    assert baixado['situacao'] == 'quitado'

    painel = corpo_de(cliente_http.get('/api/v2/painel'))
    assert painel['financeiro']['saldo_em_contas_centavos'] == primeiro['saldo_centavos']
    assert painel['estoque']['produtos_ativos'] == 1


def test_transicao_invalida_devolve_409(cliente_http, dados_base):
    venda = corpo_de(post(cliente_http, '/api/v2/vendas', {
        'parceiro_id': dados_base['cliente']['id'],
        'itens': [{'produto_id': dados_base['poltrona']['id'], 'quantidade': 1}]}))
    # rascunho -> faturado nao existe na maquina de estados
    resposta = post(cliente_http, '/api/v2/vendas/%d/faturamento' % venda['id'],
                    {'primeiro_vencimento': '2030-01-01'})
    assert resposta.status_code == 409
    assert corpo_de(resposta)['codigo'] == 'conflito_de_estado'


def test_regra_de_negocio_devolve_422(cliente_http, dados_base):
    """Sintaxe certa, regra violada: 422 separa isso de 400."""
    resposta = post(cliente_http, '/api/v2/vendas', {
        'parceiro_id': dados_base['fornecedor']['id']})   # nao e cliente
    assert resposta.status_code == 422
    assert corpo_de(resposta)['codigo'] == 'regra_violada'


def test_entrega_usa_o_endereco_do_cadastro(cliente_http, dados_base):
    """O endereco vem do cadastro, nao do corpo da requisicao."""
    entrega = corpo_de(post(cliente_http, '/api/v2/entregas', {
        'parceiro_id': dados_base['cliente']['id'],
        'data_prevista': '2030-05-01', 'hora_prevista': '14:30'}))
    assert 'Joinville' in entrega['endereco']


def test_entrega_encerrada_nao_muda_mais_de_situacao(cliente_http, dados_base):
    entrega = corpo_de(post(cliente_http, '/api/v2/entregas', {
        'parceiro_id': dados_base['cliente']['id'], 'data_prevista': '2030-05-01'}))
    rota = '/api/v2/entregas/%d/situacao' % entrega['id']
    assert put(cliente_http, rota, {'situacao': 'concluida'}).status_code == 200
    assert put(cliente_http, rota, {'situacao': 'pendente'}).status_code == 422
