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
    limite_original = modulo_app.app.config.get('RATELIMIT_ENABLED', True)
    modulo_app.app.config['RATELIMIT_ENABLED'] = False
    try:
        yield modulo_app, database
    finally:
        # Religado no finally porque o resto da suite conta com ele. Deixar
        # desligado por causa de uma falha aqui derrubaria arquivos inteiros
        # depois, e a causa apareceria longe daqui.
        modulo_app.app.config['TESTING'] = True
        modulo_app.app.config['RATELIMIT_ENABLED'] = limite_original


@pytest.fixture
def sem_sessao(app_real):
    modulo_app, _ = app_real
    with modulo_app.app.test_client() as cliente:
        yield cliente


@pytest.fixture
def com_sessao(app_real):
    modulo_app, database = app_real
    with modulo_app.app.test_client() as cliente:
        _criar_sessao_local(database, cliente, 'operador', 'administrador')
        yield cliente


def _criar_sessao_local(database, cliente, username='operador', role='usuario', ativo=True):
    """Cria usuário e apresenta o cookie de sessão exigido pelo backend."""
    user_id = database.criar_usuario(username, 'senha-local-de-teste', role, username + '@exemplo.local')
    token = 'token-local-de-teste-' + str(user_id)
    database.salvar_sessao_local(token, user_id, username, role)
    cliente.set_cookie(database.NOME_COOKIE_SESSAO_LOCAL, token)
    if not ativo:
        database.atualizar_usuario_local(user_id, ativo=0)
    return user_id


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


def test_setup_inicial_cria_desenvolvedor_uma_unica_vez(app_real):
    modulo_app, database = app_real
    cabecalhos_setup = {**CABECALHOS, 'Origin': 'http://localhost'}
    with modulo_app.app.test_client() as cliente:
        estado = cliente.get('/api/auth/local/status', headers=CABECALHOS).get_json()
        assert estado['setup_required'] is True

        resposta = cliente.post(
            '/api/auth/local/setup',
            json={
                'username': 'proprietario',
                'senha': 'uma-senha-forte-de-teste',
                'email': 'dev@exemplo.local',
            },
            headers=cabecalhos_setup,
        )
        assert resposta.status_code == 201
        cookies = '\n'.join(resposta.headers.getlist('Set-Cookie'))
        assert 'HttpOnly' in cookies
        assert 'SameSite=Strict' in cookies
        assert resposta.get_json()['usuario']['role'] == 'desenvolvedor'
        assert cliente.get('/api/auth/local/me', headers=CABECALHOS).get_json()['logado'] is True

        novamente = cliente.post(
            '/api/auth/local/setup',
            json={'username': 'outro', 'senha': 'mais-uma-senha-longa-e-forte'},
            headers=cabecalhos_setup,
        )
        assert novamente.status_code == 409
    assert database.contar_usuarios() == 1


def test_setup_inicial_exige_senha_forte(app_real):
    modulo_app, _ = app_real
    with modulo_app.app.test_client() as cliente:
        resposta = cliente.post(
            '/api/auth/local/setup',
            json={'username': 'proprietario', 'senha': 'curta'},
            headers={**CABECALHOS, 'Origin': 'http://localhost'},
        )
    assert resposta.status_code == 400


def test_login_e_cadastro_rejeitam_nome_acima_de_80_caracteres(app_real):
    modulo_app, _ = app_real
    cabecalhos = {**CABECALHOS, 'Origin': 'http://localhost'}
    username = 'u' * 81
    with modulo_app.app.test_client() as cliente:
        login = cliente.post(
            '/api/auth/local/login',
            json={'username': username, 'senha': 'senha-de-teste'},
            headers=cabecalhos,
        )
        cadastro = cliente.post(
            '/api/auth/local/register',
            json={'username': username, 'senha': 'senha-de-teste'},
            headers=cabecalhos,
        )
    assert login.status_code == 400
    assert cadastro.status_code == 400


def test_casca_da_pwa_carrega_sem_sessao(sem_sessao):
    """Sem isto o operador nao teria onde clicar em 'Conectar'."""
    for rota in ('/', '/manifest.json', '/sw.js'):
        assert sem_sessao.get(rota, headers=CABECALHOS).status_code == 200




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


# =============================================================================
# Autenticacao local: OAuth Microsoft nao concede acesso ao ERP.
# =============================================================================
def test_sessao_local_funciona_independente_da_allowlist_microsoft(app_real, monkeypatch):
    modulo_app, database = app_real
    import config
    monkeypatch.setattr(config, 'CONTAS_AUTORIZADAS', frozenset({'outra@exemplo.local'}))

    with modulo_app.app.test_client() as cliente:
        _criar_sessao_local(database, cliente, 'conta-local', 'usuario')
        assert cliente.get('/api/clientes', headers=CABECALHOS).status_code == 200


def test_sessao_microsoft_sozinha_nao_autentica_api_local(app_real):
    modulo_app, database = app_real
    database.salvar_sessao('token-microsoft', 'conta@exemplo.local')

    with modulo_app.app.test_client() as cliente:
        resposta = cliente.get('/api/clientes', headers=CABECALHOS)

    assert resposta.status_code == 401


def test_cookie_de_sessao_local_e_obrigatorio_mesmo_com_sessao_no_banco(app_real):
    modulo_app, database = app_real
    user_id = database.criar_usuario('sem-cookie', 'senha-local-de-teste', 'usuario')
    database.salvar_sessao_local('token-somente-no-banco', user_id, 'sem-cookie', 'usuario')

    with modulo_app.app.test_client() as cliente:
        assert cliente.get('/api/clientes', headers=CABECALHOS).status_code == 401


def test_controles_de_desenvolvedor_exigem_cookie_de_sessao(app_real):
    modulo_app, database = app_real
    user_id = database.criar_usuario('dev-sem-cookie', 'senha-local-de-teste', 'desenvolvedor')
    database.salvar_sessao_local('token-dev-sem-cookie', user_id, 'dev-sem-cookie', 'desenvolvedor')
    with modulo_app.app.test_client() as cliente:
        resposta = cliente.get('/api/auth/local/usuarios', headers=CABECALHOS)
    assert resposta.status_code == 401


def test_desenvolvedor_gerencia_teste_individual(app_real):
    modulo_app, database = app_real
    cliente_id = database.criar_usuario('cliente-teste', 'senha-local-de-teste', 'usuario')
    cabecalhos = {**CABECALHOS, 'Origin': 'http://localhost'}
    with modulo_app.app.test_client() as cliente:
        _criar_sessao_local(database, cliente, 'dev-teste', 'desenvolvedor')
        liberar = cliente.post(
            f'/api/auth/local/usuarios/{cliente_id}/teste',
            json={'acao': 'liberar_30_dias'}, headers=cabecalhos,
        )
        assert liberar.status_code == 200
        assert liberar.get_json()['teste']['estado'] == 'teste'

        desativar = cliente.post(
            f'/api/auth/local/usuarios/{cliente_id}/teste',
            json={'acao': 'desativar'}, headers=cabecalhos,
        )
        assert desativar.status_code == 200
        assert desativar.get_json()['teste']['estado'] == 'desativada'


def test_usuario_comum_nao_gerencia_periodo_de_teste(app_real):
    modulo_app, database = app_real
    cliente_id = database.criar_usuario('alvo-teste', 'senha-local-de-teste', 'usuario')
    cabecalhos = {**CABECALHOS, 'Origin': 'http://localhost'}
    with modulo_app.app.test_client() as cliente:
        _criar_sessao_local(database, cliente, 'usuario-teste', 'usuario')
        resposta = cliente.post(
            f'/api/auth/local/usuarios/{cliente_id}/teste',
            json={'acao': 'desativar'}, headers=cabecalhos,
        )
    assert resposta.status_code == 403


def test_conta_local_desativada_perde_a_sessao_ativa(app_real):
    modulo_app, database = app_real
    with modulo_app.app.test_client() as cliente:
        _criar_sessao_local(database, cliente, 'inativo', 'usuario', ativo=False)
        resposta = cliente.get('/api/clientes', headers=CABECALHOS)
    assert resposta.status_code == 401
    assert database.obter_sessao_local() is None
