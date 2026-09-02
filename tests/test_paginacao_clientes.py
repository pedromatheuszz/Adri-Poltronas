"""
Paginacao da lista de clientes.

Ate a versao 1.1 a tela pedia TODOS os clientes e desenhava todos de uma vez.
Com alguns milhares de registros isso e uma pausa visivel a cada troca de aba;
com dezenas de milhares, a aba trava -- montar dezenas de milhares de `<tr>`
por concatenacao de string nao tem como sair barato.

O ponto delicado nao e o SQL, e a interacao com o cache offline:
`sincronizarCache` trata a lista recebida como AUTORITATIVA e poda o que nao
esta nela. Se a paginacao virasse o padrao, a segunda pagina inteira seria
lida como "excluida no servidor" e sumiria do cache. Por isso a rota so pagina
quando `limite` e informado -- e o teste abaixo protege esse contrato.
"""
import json
import os
import sys

import pytest

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(RAIZ, 'backend'))

import database  # noqa: E402
import app as app_module  # noqa: E402
from blueprints.clientes import LIMITE_MAXIMO_POR_PAGINA  # noqa: E402

ORIGEM_LOCAL = 'http://localhost'
QUANTOS = 30


@pytest.fixture
def client(tmp_path):
    caminho = str(tmp_path / "paginacao.db")
    original = database.DB_PATH
    database.DB_PATH = caminho
    app_module.app.config['TESTING'] = True
    with app_module.app.app_context():
        database.criar_tabela()
        with database.conectar() as conexao:
            conexao.executemany(
                "INSERT INTO clientes (nome, cep, rua, bairro, cidade, entrega_retirada) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                [(f"Cliente {i:03d}", "11000-000", "Rua X", "Centro",
                  "Santos" if i % 2 else "Guaruja", "Entrega")
                 for i in range(QUANTOS)],
            )

    yield app_module.app.test_client()

    database.DB_PATH = original


def _lista(client, query=''):
    resposta = client.get('/api/clientes' + query)
    return resposta, json.loads(resposta.data)


# =============================================================================
# O contrato que o cache offline depende
# =============================================================================
def test_sem_limite_devolve_a_base_inteira(client):
    """A sincronizacao do cache poda o que nao esta na lista. Paginar por
    padrao faria a segunda pagina ser lida como 'excluida no servidor'."""
    _, dados = _lista(client)
    assert len(dados) == QUANTOS


def test_resposta_continua_sendo_um_array(client):
    """Trocar por um envelope quebraria todo consumidor existente por um dado
    que cabe num cabecalho."""
    _, dados = _lista(client, '?limite=10')
    assert isinstance(dados, list)


# =============================================================================
# Paginacao
# =============================================================================
def test_limite_recorta_a_pagina(client):
    _, dados = _lista(client, '?limite=10')
    assert len(dados) == 10


def test_deslocamento_avanca_sem_repetir(client):
    _, primeira = _lista(client, '?limite=10&deslocamento=0')
    _, segunda = _lista(client, '?limite=10&deslocamento=10')

    ids_primeira = {c['id'] for c in primeira}
    ids_segunda = {c['id'] for c in segunda}
    assert not (ids_primeira & ids_segunda), "as paginas se sobrepoem"


def test_ultima_pagina_traz_o_resto(client):
    _, dados = _lista(client, f'?limite=10&deslocamento={QUANTOS - 4}')
    assert len(dados) == 4


def test_deslocamento_alem_do_fim_devolve_vazio(client):
    _, dados = _lista(client, '?limite=10&deslocamento=9999')
    assert dados == []


def test_total_vai_no_cabecalho(client):
    """Saber que existem 450 registros e ver 200 e diferente de achar que ha
    200. Sem o total, a tela nao tem como dizer isso."""
    resposta, _ = _lista(client, '?limite=10')
    assert resposta.headers['X-Total-Registros'] == str(QUANTOS)


def test_total_acompanha_a_busca(client):
    resposta, dados = _lista(client, '?busca=Guaruja&limite=5')
    assert len(dados) == 5
    assert int(resposta.headers['X-Total-Registros']) == QUANTOS // 2


def test_paginar_percorre_a_base_inteira_sem_buraco(client):
    """A propriedade que importa: nenhum cliente fica inalcancavel."""
    vistos = []
    deslocamento = 0
    while True:
        _, pagina = _lista(client, f'?limite=7&deslocamento={deslocamento}')
        if not pagina:
            break
        vistos += [c['id'] for c in pagina]
        deslocamento += 7

    assert len(vistos) == QUANTOS
    assert len(set(vistos)) == QUANTOS


# =============================================================================
# Bordas
# =============================================================================
def test_limite_absurdo_e_aparado_pelo_teto(client):
    """Sem teto, `limite=999999` anularia a propria paginacao."""
    resposta, dados = _lista(client, '?limite=999999')
    assert len(dados) == QUANTOS  # a base e menor que o teto
    assert LIMITE_MAXIMO_POR_PAGINA < 999999


def test_limite_nao_numerico_e_recusado(client):
    resposta, dados = _lista(client, '?limite=abc')
    assert resposta.status_code == 400
    assert 'limite' in dados['erro']


def test_deslocamento_negativo_e_recusado(client):
    resposta, dados = _lista(client, '?limite=10&deslocamento=-5')
    assert resposta.status_code == 400


def test_deslocamento_zero_e_valido(client):
    """Zero e a primeira pagina. `inteiro_positivo` o recusaria, e por isso a
    checagem e feita a mao."""
    resposta, dados = _lista(client, '?limite=5&deslocamento=0')
    assert resposta.status_code == 200
    assert len(dados) == 5


def test_contagem_ignora_cliente_inativo(client):
    """Exclusao e logica. O total precisa concordar com a lista -- senao a
    tela pede uma pagina que nunca chega e o botao 'carregar mais' nao some."""
    with database.conectar() as conexao:
        conexao.execute("UPDATE clientes SET ativo = 0 WHERE id = 1")

    resposta, dados = _lista(client, '?limite=500')
    assert int(resposta.headers['X-Total-Registros']) == QUANTOS - 1
    assert len(dados) == QUANTOS - 1
