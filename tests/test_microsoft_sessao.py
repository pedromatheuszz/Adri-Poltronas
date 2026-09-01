"""
Renovacao silenciosa do token Microsoft.

O access_token que a Microsoft emite vale cerca de uma hora. Ate a versao
anterior a sessao guardava so esse token, sem validade e sem refresh_token:
passada a hora, `/api/auth/status` continuava respondendo "logado", a tela
mostrava "Conectado (fulano)" com o botao de exportar habilitado, e a falha
so aparecia depois do clique -- com os clientes ja selecionados.

Estes testes cobrem o caminho que evita isso: `offline_access` nos escopos,
refresh_token e validade gravados, e renovacao antes de cada uso do Graph.

Nenhum teste toca a rede: `urllib.request.urlopen` e substituido por um duplo.
"""
import io
import json
import os
import sys
import tempfile
import time
import urllib.error

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

import app as app_module  # noqa: E402
import config  # noqa: E402
import database  # noqa: E402
import microsoft  # noqa: E402

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


class _RespostaFalsa:
    def __init__(self, corpo, status=200):
        self._corpo = corpo if isinstance(corpo, bytes) else json.dumps(corpo).encode()
        self.status = status

    def read(self):
        return self._corpo

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


def _erro_http(codigo, corpo):
    texto = corpo if isinstance(corpo, bytes) else json.dumps(corpo).encode()
    return urllib.error.HTTPError('https://exemplo', codigo, 'erro', {}, io.BytesIO(texto))


@pytest.fixture
def urlopen_falso(monkeypatch):
    registro = {'requisicoes': [], 'respostas': []}

    def _urlopen(req, *_args, **_kwargs):
        registro['requisicoes'].append(req)
        resposta = registro['respostas'].pop(0)
        if isinstance(resposta, Exception):
            raise resposta
        return resposta

    monkeypatch.setattr('urllib.request.urlopen', _urlopen)
    return registro


def _corpo_da_requisicao(req) -> dict:
    """Decodifica o form-urlencoded enviado ao endpoint de token."""
    import urllib.parse
    return dict(urllib.parse.parse_qsl(req.data.decode('utf-8')))


# =============================================================================
# Escopos
# =============================================================================
def test_escopos_pedem_offline_access():
    """Sem `offline_access` a Microsoft nao devolve refresh_token."""
    assert 'offline_access' in config.ESCOPOS_MICROSOFT
    assert 'Files.ReadWrite' in config.ESCOPOS_MICROSOFT


def test_login_e_callback_usam_a_mesma_constante_de_escopos():
    """
    Escopos diferentes entre a autorizacao e a troca do code fazem a Microsoft
    recusar com `invalid_grant`. Antes eles eram literais em dois arquivos.
    """
    raiz = os.path.join(os.path.dirname(__file__), '..', 'backend')
    for caminho in (os.path.join(raiz, 'app.py'),
                    os.path.join(raiz, 'blueprints', 'auth.py')):
        with open(caminho, encoding='utf-8') as arquivo:
            codigo = arquivo.read()
        assert 'ESCOPOS_MICROSOFT' in codigo, f'{caminho} nao usa a constante'
        assert "'User.Read Files.ReadWrite'" not in codigo, (
            f'{caminho} voltou a escrever os escopos como literal'
        )


def test_url_de_login_carrega_offline_access(client, monkeypatch):
    abertas = []
    monkeypatch.setattr('webbrowser.open', lambda url: abertas.append(url))
    config._oauth_pending.clear()

    client.get('/api/auth/login')

    assert 'offline_access' in abertas[0]


# =============================================================================
# Validade do token
# =============================================================================
def test_sessao_sem_validade_gravada_e_tratada_como_valida():
    """
    Instalacao anterior a esta versao nao tem `expira_em`. Declarar essa
    sessao expirada desconectaria todo mundo na atualizacao; o comportamento
    antigo (deixar o Graph recusar) e preservado.
    """
    assert microsoft.token_expirado(None) is False


def test_token_com_folga_nao_e_renovado():
    assert microsoft.token_expirado(int(time.time()) + 3600) is False


def test_token_vencido_precisa_renovar():
    assert microsoft.token_expirado(int(time.time()) - 10) is True


def test_token_dentro_da_margem_renova_antes_de_vencer():
    """
    A margem existe para um envio de planilha que comece perto do limite nao
    morrer no meio, e para absorver diferenca de relogio com a Microsoft.
    """
    quase = int(time.time()) + (microsoft.MARGEM_RENOVACAO_S - 30)
    assert microsoft.token_expirado(quase) is True


def test_expiracao_ausente_cai_no_padrao_conservador():
    antes = int(time.time())
    assert microsoft.calcular_expiracao(None) >= antes + microsoft.VALIDADE_PADRAO_S - 1
    assert microsoft.calcular_expiracao('texto-invalido') >= antes + microsoft.VALIDADE_PADRAO_S - 1


# =============================================================================
# Renovacao
# =============================================================================
def test_token_valido_nao_dispara_chamada_a_microsoft(client, urlopen_falso):
    database.salvar_sessao('token-vivo', 'maria@exemplo.com',
                           refresh_token='refresh-1',
                           expira_em=int(time.time()) + 3600)

    assert microsoft.obter_token_valido() == 'token-vivo'
    assert urlopen_falso['requisicoes'] == []


def test_token_vencido_e_renovado_em_silencio(client, urlopen_falso):
    database.salvar_sessao('token-velho', 'maria@exemplo.com',
                           refresh_token='refresh-1',
                           expira_em=int(time.time()) - 10)
    urlopen_falso['respostas'] = [
        _RespostaFalsa({'access_token': 'token-novo', 'expires_in': 3600})
    ]

    assert microsoft.obter_token_valido() == 'token-novo'

    enviado = _corpo_da_requisicao(urlopen_falso['requisicoes'][0])
    assert enviado['grant_type'] == 'refresh_token'
    assert enviado['refresh_token'] == 'refresh-1'
    assert 'offline_access' in enviado['scope']

    # A sessao continua de pe, agora com o token novo e validade nova.
    sessao = database.obter_sessao()
    assert sessao['token'] == 'token-novo'
    assert sessao['conta'] == 'maria@exemplo.com'
    assert sessao['expira_em'] > int(time.time())


def test_refresh_token_rotacionado_substitui_o_anterior(client, urlopen_falso):
    """A Microsoft entrega um refresh_token novo em parte das renovacoes."""
    database.salvar_sessao('token-velho', 'maria@exemplo.com',
                           refresh_token='refresh-1',
                           expira_em=int(time.time()) - 10)
    urlopen_falso['respostas'] = [
        _RespostaFalsa({'access_token': 'token-novo', 'expires_in': 3600,
                        'refresh_token': 'refresh-2'})
    ]

    microsoft.obter_token_valido()

    assert database.obter_sessao()['refresh_token'] == 'refresh-2'


def test_refresh_token_ausente_na_resposta_preserva_o_antigo(client, urlopen_falso):
    """Apagar o refresh_token quando ele nao vem na resposta mataria a sessao."""
    database.salvar_sessao('token-velho', 'maria@exemplo.com',
                           refresh_token='refresh-1',
                           expira_em=int(time.time()) - 10)
    urlopen_falso['respostas'] = [
        _RespostaFalsa({'access_token': 'token-novo', 'expires_in': 3600})
    ]

    microsoft.obter_token_valido()

    assert database.obter_sessao()['refresh_token'] == 'refresh-1'


def test_renovacao_recusada_encerra_a_sessao(client, urlopen_falso):
    """
    Consentimento retirado ou refresh_token revogado: nao ha o que renovar, e
    manter a sessao local faria a tela seguir mostrando "Conectado".
    """
    database.salvar_sessao('token-velho', 'maria@exemplo.com',
                           refresh_token='refresh-revogado',
                           expira_em=int(time.time()) - 10)
    urlopen_falso['respostas'] = [_erro_http(400, {'error': 'invalid_grant'})]

    assert microsoft.obter_token_valido() is None
    assert database.obter_sessao() is None


def test_sessao_vencida_sem_refresh_token_e_encerrada(client, urlopen_falso):
    """Sessao de uma versao anterior, ja com validade gravada por engano."""
    database.salvar_sessao('token-velho', 'maria@exemplo.com',
                           expira_em=int(time.time()) - 10)

    assert microsoft.obter_token_valido() is None
    assert database.obter_sessao() is None
    assert urlopen_falso['requisicoes'] == []


def test_queda_de_rede_nao_confirma_nem_nega_e_pede_reconexao(client, urlopen_falso):
    database.salvar_sessao('token-velho', 'maria@exemplo.com',
                           refresh_token='refresh-1',
                           expira_em=int(time.time()) - 10)
    urlopen_falso['respostas'] = [urllib.error.URLError('sem rota')]

    assert microsoft.obter_token_valido() is None


# =============================================================================
# Status exposto para a tela
# =============================================================================
def test_status_reporta_desconectado_quando_nao_da_para_renovar(client, urlopen_falso):
    """
    O ponto central da correcao: a tela nao pode dizer "Conectado" para uma
    sessao que ja nao autentica.
    """
    database.salvar_sessao('token-velho', 'maria@exemplo.com',
                           refresh_token='refresh-revogado',
                           expira_em=int(time.time()) - 10)
    urlopen_falso['respostas'] = [_erro_http(400, {'error': 'invalid_grant'})]

    dados = json.loads(client.get('/api/auth/status').data)

    assert dados['logado'] is False
    assert dados['motivo'] == 'sessao_expirada'


def test_status_renova_e_segue_conectado(client, urlopen_falso):
    database.salvar_sessao('token-velho', 'maria@exemplo.com',
                           refresh_token='refresh-1',
                           expira_em=int(time.time()) - 10)
    urlopen_falso['respostas'] = [
        _RespostaFalsa({'access_token': 'token-novo', 'expires_in': 3600})
    ]

    dados = json.loads(client.get('/api/auth/status').data)

    assert dados['logado'] is True
    assert dados['conta'] == 'maria@exemplo.com'


def test_status_sem_sessao_nao_traz_motivo(client):
    dados = json.loads(client.get('/api/auth/status').data)
    assert dados['logado'] is False
    assert 'motivo' not in dados


# =============================================================================
# Callback e exportacao ponta a ponta
# =============================================================================
def test_callback_grava_refresh_token_e_validade(client, monkeypatch):
    config._oauth_pending.clear()
    config._oauth_pending['estado-z'] = {'verifier': 'v', 'ts': 0}

    respostas = [
        _RespostaFalsa({'access_token': 'token-a', 'refresh_token': 'refresh-a',
                        'expires_in': 3600}),
        _RespostaFalsa({'userPrincipalName': 'maria@exemplo.com'}),
    ]
    monkeypatch.setattr('urllib.request.urlopen', lambda *a, **k: respostas.pop(0))

    assert client.get('/callback?code=abc&state=estado-z').status_code == 200

    sessao = database.obter_sessao()
    assert sessao['token'] == 'token-a'
    assert sessao['refresh_token'] == 'refresh-a'
    assert sessao['expira_em'] > int(time.time())


def test_exportacao_renova_o_token_e_conclui(client, urlopen_falso, monkeypatch):
    """
    O cenario que o operador vivia: deixa o app aberto, volta depois do almoco
    e exporta. Antes isso dava "Sessao expirada"; agora renova sozinho.
    """
    monkeypatch.setattr('webbrowser.open', lambda _url: None)
    database.salvar_sessao('token-velho', 'maria@exemplo.com',
                           refresh_token='refresh-1',
                           expira_em=int(time.time()) - 10)
    client.post('/api/clientes', headers={'Origin': ORIGEM_LOCAL},
                data=json.dumps({'nome': 'Maria Souza', 'cep': '12345-678',
                                 'rua': 'Rua A', 'bairro': 'Centro',
                                 'cidade': 'Sao Paulo', 'entrega_retirada': 'Entrega'}),
                content_type='application/json')
    cliente_id = json.loads(client.get('/api/clientes').data)[0]['id']

    urlopen_falso['respostas'] = [
        _RespostaFalsa({'access_token': 'token-novo', 'expires_in': 3600}),
        _RespostaFalsa({'webUrl': 'https://onedrive/planilha.xlsx'}),
    ]

    resposta = client.post('/api/excel/enviar', headers={'Origin': ORIGEM_LOCAL},
                           data=json.dumps({'ids': [cliente_id], 'nome_arquivo': 'Clientes'}),
                           content_type='application/json')

    assert resposta.status_code == 200
    assert json.loads(resposta.data)['url'] == 'https://onedrive/planilha.xlsx'

    # O upload precisa ter saido com o token NOVO, e nao com o vencido.
    requisicao_upload = urlopen_falso['requisicoes'][1]
    assert requisicao_upload.get_method() == 'PUT'
    assert requisicao_upload.headers['Authorization'] == 'Bearer token-novo'


def test_exportacao_sem_renovacao_possivel_devolve_401(client, urlopen_falso):
    database.salvar_sessao('token-velho', 'maria@exemplo.com',
                           refresh_token='refresh-revogado',
                           expira_em=int(time.time()) - 10)
    urlopen_falso['respostas'] = [_erro_http(400, {'error': 'invalid_grant'})]

    resposta = client.post('/api/excel/enviar', headers={'Origin': ORIGEM_LOCAL},
                           data=json.dumps({'ids': [1]}),
                           content_type='application/json')

    assert resposta.status_code == 401
    assert database.obter_sessao() is None


# =============================================================================
# Armazenamento
# =============================================================================
def test_refresh_token_e_gravado_cifrado(client):
    """Credencial de longa duracao nao pode ficar em claro no SQLite."""
    database.salvar_sessao('token-a', 'maria@exemplo.com', refresh_token='refresh-secreto')

    with database.conectar() as conexao:
        linha = conexao.execute('SELECT token, refresh_token FROM sessao').fetchone()

    assert 'refresh-secreto' not in (linha['refresh_token'] or '')
    assert 'token-a' not in (linha['token'] or '')
    assert database.obter_sessao()['refresh_token'] == 'refresh-secreto'


def test_salvar_sessao_aceita_dois_argumentos(client):
    """Assinatura antiga continua valendo para nao quebrar chamadas existentes."""
    database.salvar_sessao('token-a', 'maria@exemplo.com')
    sessao = database.obter_sessao()
    assert sessao['token'] == 'token-a'
    assert sessao['refresh_token'] is None
    assert sessao['expira_em'] is None
