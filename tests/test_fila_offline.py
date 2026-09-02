"""
A fila offline, do lado do servidor.

A fila reenvia uma operacao sempre que a tentativa anterior nao confirmou. Mas
"nao confirmou" e ambiguo: o servidor pode nunca ter recebido, ou ter recebido,
gravado, e a resposta ter se perdido no caminho de volta. Do lado do navegador
as duas situacoes sao o mesmo `fetch` que rejeita.

Sem nada que distinga uma da outra, reenviar um POST de criacao produzia DOIS
clientes identicos -- e o operador so descobria olhando a lista.

Os testes de compactacao, remapeamento e fila de erros vivem no navegador
(`frontend/js/offline.js`); aqui esta a metade que o backend precisa oferecer:
lembrar do que ja processou, e devolver o id do cliente criado para que a fila
consiga remapear o que vem depois dele.
"""
import json
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

import database  # noqa: E402
import app as app_module  # noqa: E402
from erp.core import idempotencia  # noqa: E402

ORIGEM_LOCAL = 'http://localhost'


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


def _corpo_do_cliente(nome="Cliente Offline"):
    return {
        "nome": nome, "cep": "12345-678", "rua": "Rua Teste",
        "bairro": "Centro", "cidade": "Sao Paulo", "entrega_retirada": "Entrega",
    }


def _criar(client, chave=None, nome="Cliente Offline"):
    cabecalhos = {'Origin': ORIGEM_LOCAL, 'Content-Type': 'application/json'}
    if chave:
        cabecalhos[idempotencia.NOME_DO_HEADER] = chave
    return client.post('/api/clientes', headers=cabecalhos,
                       data=json.dumps(_corpo_do_cliente(nome)))


def _quantos_clientes(client):
    return len(json.loads(client.get('/api/clientes').data))


# =============================================================================
# O id na resposta: sem ele a fila nao consegue remapear
# =============================================================================
def test_criacao_devolve_o_id_do_cliente(client):
    """
    A fila cria o cliente com id temporario negativo e precisa do id real para
    remapear as operacoes seguintes. Sem ele, a edicao feita logo apos criar
    offline era enviada contra o id negativo, tomava 404 e era descartada em
    silencio -- a edicao do operador sumia.
    """
    resposta = _criar(client)

    assert resposta.status_code == 201
    corpo = json.loads(resposta.data)
    assert isinstance(corpo.get('id'), int)
    assert database.obter_cliente_por_id(corpo['id'])['nome'] == 'Cliente Offline'


# =============================================================================
# Idempotencia
# =============================================================================
def test_reenvio_com_a_mesma_chave_nao_cria_dois_clientes(client):
    """O defeito: a resposta se perde, a fila reenvia, e nascem dois."""
    primeira = _criar(client, chave='op-abc-123')
    segunda = _criar(client, chave='op-abc-123')

    assert primeira.status_code == 201
    assert segunda.status_code == 201
    assert _quantos_clientes(client) == 1, "o reenvio criou um segundo cliente"


def test_reenvio_devolve_a_mesma_resposta(client):
    """Nao basta nao duplicar: a repeticao precisa devolver o MESMO id, senao
    a fila remapeia para um registro que nao existe."""
    primeira = json.loads(_criar(client, chave='op-abc-123').data)
    segunda_resposta = _criar(client, chave='op-abc-123')
    segunda = json.loads(segunda_resposta.data)

    assert segunda['id'] == primeira['id']
    assert segunda_resposta.headers.get('X-Idempotencia') == 'repetida'


def test_chaves_diferentes_criam_clientes_diferentes(client):
    """Duas operacoes distintas continuam sendo duas operacoes."""
    _criar(client, chave='op-1', nome='Primeiro')
    _criar(client, chave='op-2', nome='Segundo')

    assert _quantos_clientes(client) == 2


def test_sem_chave_a_rota_se_comporta_como_antes(client):
    """O mecanismo e para quem envia da fila, nao para a tela. Um formulario
    submetido duas vezes continua criando dois cadastros -- a decisao ali e do
    operador, e transformar isso em silencio esconderia o engano dele."""
    _criar(client, nome='Sem chave')
    _criar(client, nome='Sem chave')

    assert _quantos_clientes(client) == 2


def test_erro_de_validacao_nao_e_lembrado(client):
    """Reenviar um 400 produz o mesmo 400, sem efeito colateral. Guardar erro
    so faria a tabela crescer com o que nao interessa -- e impediria a fila de
    reenviar depois que a causa fosse corrigida."""
    invalido = {"nome": "", "cep": "", "rua": "", "bairro": "", "cidade": "",
                "entrega_retirada": "Entrega"}
    cabecalhos = {'Origin': ORIGEM_LOCAL, 'Content-Type': 'application/json',
                  idempotencia.NOME_DO_HEADER: 'op-invalida'}

    recusada = client.post('/api/clientes', headers=cabecalhos, data=json.dumps(invalido))
    assert recusada.status_code == 400

    corrigida = _criar(client, chave='op-invalida', nome='Agora vai')
    assert corrigida.status_code == 201
    assert _quantos_clientes(client) == 1


def test_exclusao_repetida_nao_vira_404(client):
    """
    Sem idempotencia, a segunda tentativa de uma exclusao ja aplicada recebia
    404 e a fila a movia para a fila de erros -- avisando o operador de um
    problema que nao existe.
    """
    cliente_id = json.loads(_criar(client).data)['id']
    cabecalhos = {'Origin': ORIGEM_LOCAL, idempotencia.NOME_DO_HEADER: 'op-del-1'}

    primeira = client.delete(f'/api/clientes/{cliente_id}', headers=cabecalhos)
    segunda = client.delete(f'/api/clientes/{cliente_id}', headers=cabecalhos)

    assert primeira.status_code == 200
    assert segunda.status_code == 200


# =============================================================================
# Manutencao da tabela
# =============================================================================
def test_chave_absurda_e_ignorada(client):
    """Uma chave sem limite viraria uma linha sem limite no banco."""
    assert idempotencia.chave_valida('x' * idempotencia.TAMANHO_MAXIMO_DA_CHAVE) is True
    assert idempotencia.chave_valida('x' * (idempotencia.TAMANHO_MAXIMO_DA_CHAVE + 1)) is False
    assert idempotencia.chave_valida('') is False
    assert idempotencia.chave_valida(None) is False


def test_lembrancas_antigas_sao_descartadas(client):
    """A fila offline nao guarda operacao por semanas. Sem a poda, a tabela so
    cresce na maquina do usuario."""
    _criar(client, chave='op-velha')

    with database.conectar() as conexao:
        conexao.execute(
            "UPDATE operacoes_idempotentes SET criado_em = datetime('now', '-30 days')"
        )

    removidas = idempotencia.limpar_antigas(database.conectar)

    assert removidas == 1
    assert idempotencia.resposta_registrada(database.conectar, 'op-velha') is None


def test_banco_sem_a_tabela_nao_derruba_a_escrita(client, monkeypatch):
    """Instalacao antiga ou schema de emergencia: perder idempotencia e ruim,
    recusar a escrita seria pior."""
    with database.conectar() as conexao:
        conexao.execute("DROP TABLE operacoes_idempotentes")

    resposta = _criar(client, chave='op-sem-tabela')

    assert resposta.status_code == 201
