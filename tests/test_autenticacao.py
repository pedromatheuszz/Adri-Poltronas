"""
O guarda de autenticacao, exercitado com TESTING desligado.

POR QUE ESTE ARQUIVO EXISTE
A primeira linha de `_verificar_autenticacao` e:

    if app.config.get('TESTING'):
        return None

e praticamente toda a suite roda com `TESTING` ligado. O resultado e que a
regra mais basica do backend -- "sem sessao nao se fala com a API" -- nao
tinha um unico teste que a provasse. Uma alteracao que abrisse a API por
engano passava com a suite inteira verde, e a cobertura de linhas nao ajudava:
ela mede linha executada, nao comportamento do guarda em modo real.

Foi assim que sobreviveu, ate a 1.3.0, a folga que permitia QUALQUER GET em
/api/ sem sessao -- incluindo `/api/backup/sqlite`, que devolve o banco
inteiro com nome, CEP e endereco de todos os clientes.

COMO ESTES TESTES SAO MONTADOS
Com `TESTING` desligado, os guardas do `before_request` rodam na ordem real:
host de loopback, capacidade, origem, autenticacao. Para medir o de
autenticacao e preciso passar pelos anteriores -- por isso o token de
capacidade e apresentado em toda requisicao. Sem ele a resposta seria 403 do
guarda de capacidade, e o teste estaria verde pelo motivo errado.
"""
import os
import sys

import pytest

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(RAIZ, 'backend'))

import capacidade  # noqa: E402

TOKEN_DE_CAPACIDADE = 'token-do-app-nos-testes'
CABECALHOS = {capacidade.NOME_DO_HEADER: TOKEN_DE_CAPACIDADE}


@pytest.fixture
def app_real(monkeypatch, tmp_path):
    """O app com os guardas ligados, sobre um banco descartavel e vazio."""
    banco = str(tmp_path / 'auth.db')
    monkeypatch.setenv('ADRI_DB_PATH', banco)
    monkeypatch.setenv(capacidade.VARIAVEL_DE_AMBIENTE, TOKEN_DE_CAPACIDADE)
    monkeypatch.delenv(capacidade.VARIAVEL_DE_DESLIGAMENTO, raising=False)

    import app as modulo_app
    import database

    monkeypatch.setattr(database, 'DB_PATH', banco)
    database.criar_tabela()

    modulo_app.app.config['TESTING'] = False
    try:
        yield modulo_app, database
    finally:
        # Religado no finally porque o resto da suite conta com ele. Deixar
        # desligado por causa de uma falha aqui derrubaria arquivos inteiros
        # depois, e a causa apareceria longe daqui.
        modulo_app.app.config['TESTING'] = True


@pytest.fixture
def sem_sessao(app_real):
    modulo_app, _ = app_real
    with modulo_app.app.test_client() as cliente:
        yield cliente


@pytest.fixture
def com_sessao(app_real):
    modulo_app, database = app_real
    database.salvar_sessao('token-de-teste', 'operador@exemplo.local')
    with modulo_app.app.test_client() as cliente:
        yield cliente


# =============================================================================
# Escrita
#
# Esta regra ja valia antes da 1.3.1 -- e mesmo assim nao tinha teste.
# =============================================================================
ROTAS_DE_ESCRITA = [
    ('POST', '/api/clientes'),
    ('PUT', '/api/clientes/1'),
    ('DELETE', '/api/clientes/1'),
    ('POST', '/api/pagamentos'),
    ('PUT', '/api/pagamentos/1'),
    ('DELETE', '/api/pagamentos/1'),
    ('POST', '/api/backup/criar'),
    ('POST', '/api/backup/restaurar'),
]


@pytest.mark.parametrize('metodo,rota', ROTAS_DE_ESCRITA)
def test_escrita_sem_sessao_e_recusada(sem_sessao, metodo, rota):
    resposta = sem_sessao.open(rota, method=metodo, json={}, headers=CABECALHOS)
    assert resposta.status_code == 401


# =============================================================================
# Leitura -- o que a 1.3.1 fecha
# =============================================================================
ROTAS_DE_LEITURA = [
    '/api/clientes',
    '/api/clientes/mapa',
    '/api/pagamentos',
    '/api/pagamentos/metricas',
    '/api/relatorios',
    '/api/entregas',
]


@pytest.mark.parametrize('rota', ROTAS_DE_LEITURA)
def test_leitura_sem_sessao_e_recusada(sem_sessao, rota):
    resposta = sem_sessao.get(rota, headers=CABECALHOS)
    assert resposta.status_code == 401


# =============================================================================
# Exportacao em massa
#
# Separadas das demais leituras de proposito: sao as que devolvem o cadastro
# inteiro num arquivo so, e portanto as que transformam a folga num vazamento
# completo em uma requisicao. Merecem assercao propria para que, se alguem um
# dia reabrir a leitura "so para a tela inicial funcionar", estas continuem
# fechadas e o teste diga isso.
# =============================================================================
ROTAS_DE_EXPORTACAO = [
    '/api/backup/sqlite',
    '/api/backup/json',
    '/api/clientes/backup/sqlite',
    '/api/clientes/backup/json',
    '/api/relatorios/exportar',
]


@pytest.mark.parametrize('rota', ROTAS_DE_EXPORTACAO)
def test_exportacao_em_massa_sem_sessao_e_recusada(sem_sessao, rota):
    resposta = sem_sessao.get(rota, headers=CABECALHOS)
    assert resposta.status_code == 401
    # O corpo nao pode conter o banco: 401 com 200 KB anexados seria a mesma
    # falha com outro codigo de status.
    assert len(resposta.data) < 1024


# =============================================================================
# O que precisa responder ANTES do login
#
# Uma isencao a mais e uma porta aberta; uma a menos e um app que nao abre.
# =============================================================================
def test_sonda_de_identidade_responde_sem_sessao(sem_sessao):
    """O Electron pergunta a /api/health quem esta na porta antes de adotar o
    backend -- muito antes de existir login."""
    resposta = sem_sessao.get('/api/health', headers=CABECALHOS)
    assert resposta.status_code == 200
    assert resposta.get_json()['servico'] == 'adri-poltronas'


def test_status_de_login_responde_sem_sessao(sem_sessao):
    """E a rota que a interface consulta para saber se precisa pedir login.
    Exigir sessao nela seria pedir a chave para entregar a chave."""
    resposta = sem_sessao.get('/api/auth/status', headers=CABECALHOS)
    assert resposta.status_code == 200
    assert resposta.get_json()['logado'] is False


def test_casca_da_pwa_carrega_sem_sessao(sem_sessao):
    """Sem isto o operador nao teria onde clicar em 'Conectar'."""
    for rota in ('/', '/manifest.json', '/sw.js'):
        assert sem_sessao.get(rota, headers=CABECALHOS).status_code == 200


def test_isencoes_sao_apenas_as_declaradas():
    """Guarda contra o crescimento silencioso da lista. Cada nome aqui foi
    justificado no comentario que acompanha ROTAS_SEM_AUTH."""
    import app as modulo_app
    assert modulo_app.ROTAS_SEM_AUTH == frozenset({
        '/api/auth/login', '/api/auth/status', '/api/auth/logout',
        '/api/health',
        '/', '/manifest.json', '/sw.js',
        '/callback', '/api/pagamentos/webhook',
    })


# =============================================================================
# Com sessao, o sistema funciona
#
# Sem estes, "recusa tudo" passaria nos testes acima e seria uma regressao
# igualmente grave -- so que na direcao oposta.
# =============================================================================
def test_leitura_com_sessao_funciona(com_sessao):
    resposta = com_sessao.get('/api/clientes', headers=CABECALHOS)
    assert resposta.status_code == 200


def test_exportacao_com_sessao_funciona(com_sessao):
    resposta = com_sessao.get('/api/backup/sqlite', headers=CABECALHOS)
    assert resposta.status_code == 200
    assert len(resposta.data) > 1024
