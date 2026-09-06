"""
Duas requisicoes ao mesmo tempo no mesmo registro.

O app e monousuario, entao "concorrencia" aqui nao e carga: e o duplo clique,
o Enter repetido, o botao que nao trava enquanto o POST viaja. O Flask sobe com
`threaded=True` (servidor.py), entao dois cliques viram duas threads de verdade.

O que torna isso perigoso e uma propriedade do sqlite3 do Python que nao esta
a vista: a transacao so ABRE NA PRIMEIRA ESCRITA. Todo SELECT feito antes dela
-- inclusive o que le a situacao do pedido para decidir se a operacao e valida
-- roda fora de qualquer transacao. Duas threads liam 'aprovado', as duas
passavam pela maquina de estados, o SQLite serializava so as ESCRITAS, e a
segunda gravava por cima sem reler nada.

O prejuizo era financeiro e invisivel: um pedido de R$ 100,00 em 3x virava seis
parcelas somando R$ 200,00 a receber.

Estes testes rodam threads de verdade contra um banco de verdade. Sao o tipo de
teste que passa por acidente se a correcao for removida e o agendador for
generoso -- por isso cada um roda varias rodadas e afirma sobre o ESTADO FINAL
do banco, nao sobre quem ganhou a corrida.
"""
import json
import os
import sys
import tempfile
import threading

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

import app as app_module  # noqa: E402
import database  # noqa: E402
from erp.comercial import repositorio, servico  # noqa: E402

ORIGEM = 'http://localhost'
CABECALHOS = {'Origin': ORIGEM, 'Content-Type': 'application/json'}

# Rodadas por teste. Uma corrida perdida por acaso nao prova nada; o que prova e
# o estado final estar certo em TODAS as rodadas.
RODADAS = 8


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
    try:
        os.unlink(caminho)
    except OSError:
        # No Windows o WAL pode segurar o arquivo por um instante depois do
        # ultimo close. O temporario e descartavel; nao vale derrubar o teste.
        pass


def _post(cliente, rota, corpo=None):
    return cliente.post(rota, headers=CABECALHOS, data=json.dumps(corpo or {}))


def _pedido_aprovado(client):
    cliente_id = database.salvar_cliente(
        'Dona Marta', '89200-000', 'Rua A, 10', 'Centro', 'Joinville', 'Entrega')
    produto_id = _post(client, '/api/produtos', {
        'codigo': f'POLT-{cliente_id:03d}', 'descricao': 'Poltrona Costela',
        'preco_venda': '100,00',
    }).get_json()['id']
    pedido = _post(client, '/api/pedidos', {'cliente_id': cliente_id}).get_json()
    _post(client, f"/api/pedidos/{pedido['id']}/itens",
          {'produto_id': produto_id, 'quantidade': 1})
    _post(client, f"/api/pedidos/{pedido['id']}/abertura")
    _post(client, f"/api/pedidos/{pedido['id']}/aprovacao")
    return pedido['id']


def _em_paralelo(alvo, vezes=2):
    """
    Dispara `vezes` threads que so largam juntas, e devolve o que cada uma deu.

    A barreira e o que faz o teste valer: sem ela as threads sao criadas em
    sequencia e a primeira costuma terminar antes da segunda comecar -- o teste
    passaria sem nunca ter havido corrida.
    """
    largada = threading.Barrier(vezes)
    resultados = [None] * vezes

    def _corredor(indice):
        largada.wait()
        try:
            resultados[indice] = ('ok', alvo())
        except Exception as erro:  # noqa: BLE001 - o teste classifica depois
            resultados[indice] = ('erro', erro)

    threads = [threading.Thread(target=_corredor, args=(i,)) for i in range(vezes)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    return resultados


# =============================================================================
# Faturamento (BUG-03)
# =============================================================================
def test_duplo_faturamento_simultaneo_emite_um_conjunto_de_parcelas(client):
    """
    A regressao que custa dinheiro.

    Duas chamadas simultaneas a `faturar_pedido` no mesmo pedido tem de
    terminar com EXATAMENTE 3 parcelas -- nunca 6 -- e uma das duas tem de
    falhar com conflito de situacao.
    """
    for _ in range(RODADAS):
        pedido_id = _pedido_aprovado(client)

        resultados = _em_paralelo(lambda: servico.faturar_pedido(pedido_id, {
            'parcelas': 3, 'primeiro_vencimento': '2026-10-31', 'forma_pagamento': 'Pix',
        }))

        sucessos = [r for r in resultados if r and r[0] == 'ok']
        conflitos = [r for r in resultados
                     if r and r[0] == 'erro' and isinstance(r[1], servico.ConflitoDeSituacao)]

        assert len(sucessos) == 1, f"esperava um unico faturamento, veio {resultados}"
        assert len(conflitos) == 1, f"a segunda devia ter dado conflito, veio {resultados}"

        with database.conectar() as conexao:
            parcelas = repositorio.parcelas_do_pedido(conexao, pedido_id)
            situacao = conexao.execute(
                "SELECT situacao FROM pedidos WHERE id = ?", (pedido_id,)).fetchone()[0]

        assert len(parcelas) == 3, f"parcelas duplicadas: {len(parcelas)}"
        assert sum(p['valor_centavos'] for p in parcelas) == 10000
        assert situacao == 'faturado'


def test_a_rota_de_faturamento_devolve_409_na_segunda_chamada(client):
    """O conflito precisa chegar ao operador como 409, nao como 500."""
    pedido_id = _pedido_aprovado(client)
    corpo = {'parcelas': 2, 'primeiro_vencimento': '2026-10-31', 'forma_pagamento': 'Pix'}

    primeira = _post(client, f'/api/pedidos/{pedido_id}/faturamento', corpo)
    segunda = _post(client, f'/api/pedidos/{pedido_id}/faturamento', corpo)

    assert primeira.status_code == 200
    assert segunda.status_code == 409


def test_transicao_recusa_quando_a_situacao_mudou_sob_os_pes(client):
    """
    O mecanismo isolado, sem threads: `mudar_situacao` com uma expectativa que
    ja nao vale nao pode alterar linha nenhuma.
    """
    pedido_id = _pedido_aprovado(client)
    with database.conectar() as conexao:
        assert repositorio.mudar_situacao(
            conexao, pedido_id, 'faturado', situacao_esperada='aprovado') == 1
        # Segunda tentativa com a MESMA premissa: o pedido ja nao esta aprovado.
        assert repositorio.mudar_situacao(
            conexao, pedido_id, 'faturado', situacao_esperada='aprovado') == 0


def test_transicao_recusa_coluna_fora_da_allowlist(client):
    """
    ARQ-09: nome de coluna e o unico texto que vira query neste repositorio.
    A allowlist tem de recusar antes de montar o SQL.
    """
    pedido_id = _pedido_aprovado(client)
    with database.conectar() as conexao:
        with pytest.raises(ValueError):
            repositorio.mudar_situacao(
                conexao, pedido_id, 'cancelado', {"situacao = 'x' --": 1})


# =============================================================================
# Numeracao de pedido (BUG-08)
# =============================================================================
def test_dois_pedidos_simultaneos_recebem_numeros_distintos(client):
    """
    `proximo_numero` deriva do maior numero gravado. Duas threads liam o mesmo
    ultimo numero e tentavam gravar o mesmo seguinte; o indice unico recusava a
    segunda e o handler generico devolvia 500 com id de correlacao -- um erro
    opaco para o operador, num caso em que o sistema sabe exatamente o que
    aconteceu e poderia so ter emitido o numero seguinte.
    """
    cliente_id = database.salvar_cliente(
        'Dona Marta', '89200-000', 'Rua A, 10', 'Centro', 'Joinville', 'Entrega')

    for _ in range(RODADAS):
        resultados = _em_paralelo(
            lambda: _post(client, '/api/pedidos', {'cliente_id': cliente_id}))

        codigos = [r[1].status_code for r in resultados if r and r[0] == 'ok']
        assert all(c in (200, 201, 409) for c in codigos), f"status inesperado: {codigos}"
        assert 500 not in codigos, "corrida na numeracao virou erro opaco"

    with database.conectar() as conexao:
        numeros = [linha[0] for linha in
                   conexao.execute("SELECT numero FROM pedidos").fetchall()]
    assert len(numeros) == len(set(numeros)), f"numero repetido: {numeros}"


def test_codigo_de_produto_duplicado_simultaneo_vira_erro_de_negocio(client):
    """
    `codigo_em_uso` tambem le fora de transacao: dois cadastros simultaneos com
    o mesmo codigo passam os dois pela checagem. O indice unico pega o segundo,
    e ele precisa chegar ao operador com a mesma mensagem que receberia se
    tivesse chegado um segundo depois -- nao como 500.
    """
    for rodada in range(RODADAS):
        corpo = {'codigo': f'DUP-{rodada:03d}', 'descricao': 'Poltrona',
                 'preco_venda': '10,00'}
        resultados = _em_paralelo(lambda: _post(client, '/api/produtos', corpo))

        codigos = [r[1].status_code for r in resultados if r and r[0] == 'ok']
        assert sorted(codigos) == [201, 400], f"status inesperado: {codigos}"
