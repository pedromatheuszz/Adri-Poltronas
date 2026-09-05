"""
Integracoes externas: ViaCEP, Gemini e Microsoft Graph.

Ate a 1.4.2 este arquivo cobria tambem o cliente do Asaas -- a maior parte
dele, alias. A integracao de cobranca foi removida, e com ela os testes do
cliente HTTP, da criacao de cliente no gateway e da traducao de erro.

O que ficou sao as tres integracoes que sobreviveram, e o duplo de `urlopen`
que as sustenta: nenhuma requisicao sai da maquina, e o que se exercita e a
traducao entre o formato de fora e o que o app espera.
"""
import io
import json
import os
import sys
import tempfile
import urllib.error

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

import config  # noqa: E402
import database  # noqa: E402
import app as app_module  # noqa: E402

ORIGEM_LOCAL = 'http://localhost'


@pytest.fixture
def client():
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name
    original = database.DB_PATH
    database.DB_PATH = db_path
    app_module.app.config['TESTING'] = True
    with app_module.app.app_context():
        database.criar_tabela()
    yield app_module.app.test_client()
    database.DB_PATH = original
    os.unlink(db_path)


# -----------------------------------------------------------------------------
# Duplo de urlopen
# -----------------------------------------------------------------------------
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
    return urllib.error.HTTPError(
        'https://exemplo', codigo, 'erro', {}, io.BytesIO(texto))


@pytest.fixture
def urlopen_falso(monkeypatch):
    """Substitui urlopen e registra as requisicoes feitas."""
    registro = {'requisicoes': [], 'resposta': _RespostaFalsa({})}

    def _urlopen(req, *args, **kwargs):
        registro['requisicoes'].append(req)
        resposta = registro['resposta']
        if isinstance(resposta, Exception):
            raise resposta
        return resposta

    monkeypatch.setattr('urllib.request.urlopen', _urlopen)
    return registro


# =============================================================================
# Asaas - configuracao
# =============================================================================












# =============================================================================
# Asaas - camada HTTP
# =============================================================================
















# -----------------------------------------------------------------------------
# O que a recusa do Asaas escreve no log
#
# Os tres tratadores de HTTPError gravavam o corpo BRUTO da resposta. Numa
# recusa de criacao de cliente esse corpo repete o que foi enviado -- nome,
# CPF/CNPJ, e-mail, telefone -- em texto claro, num `app.log` que fica em
# %APPDATA% sem cifragem e roda por 5 arquivos de 2 MB.
#
# Destoava do proprio projeto: os tokens da Microsoft e as chaves de
# integracao sao cifrados via DPAPI, o PRIVACIDADE.md trata dado de cliente
# como sensivel, e o roadmap ja exigia "webhook sem payload sensivel nos logs".
# A mesma regra vale para o cliente HTTP de saida.
# -----------------------------------------------------------------------------


CORPO_COM_CADASTRO = {
    "errors": [{
        "code": "invalid_cpfCnpj",
        "description": "O CPF 529.982.247-25 de Maria Souza e invalido.",
    }],
    "name": "Maria Souza",
    "cpfCnpj": "52998224725",
    "email": "maria@exemplo.com",
    "mobilePhone": "47999998888",
}

DADOS_PESSOAIS = ["Maria Souza", "52998224725", "529.982.247-25",
                  "maria@exemplo.com", "47999998888"]










# =============================================================================
# Asaas - operacoes
# =============================================================================














# =============================================================================
# IA / ViaCEP
# =============================================================================
@pytest.mark.parametrize("cep", ["123", "abcdefgh", "", "1234567890"])
def test_cep_invalido_e_recusado(client, cep):
    resposta = client.post('/api/ia/sugestao-bairro', headers={'Origin': ORIGEM_LOCAL},
        data=json.dumps({"cep": cep}), content_type='application/json')
    assert resposta.status_code == 400


def test_viacep_respondendo_devolve_o_endereco(client, urlopen_falso):
    urlopen_falso['resposta'] = _RespostaFalsa({
        "bairro": "Se", "localidade": "Sao Paulo", "logradouro": "Praca da Se", "uf": "SP"})
    resposta = client.post('/api/ia/sugestao-bairro', headers={'Origin': ORIGEM_LOCAL},
        data=json.dumps({"cep": "01001-000"}), content_type='application/json')
    dados = json.loads(resposta.data)
    assert resposta.status_code == 200
    assert dados['bairro'] == 'Se'
    assert dados['cidade'] == 'Sao Paulo'
    assert dados['fonte'] == 'ViaCEP'


def test_cep_inexistente_no_viacep_sem_gemini(client, urlopen_falso, monkeypatch):
    monkeypatch.setattr(config, 'GEMINI_API_KEY', '')
    urlopen_falso['resposta'] = _RespostaFalsa({"erro": True})
    resposta = client.post('/api/ia/sugestao-bairro', headers={'Origin': ORIGEM_LOCAL},
        data=json.dumps({"cep": "99999-999"}), content_type='application/json')
    # 502, e nao 500: quem falhou foi o ViaCEP, servico externo.
    assert resposta.status_code == 502


def test_queda_do_viacep_cai_para_o_gemini(client, monkeypatch):
    monkeypatch.setattr(config, 'GEMINI_API_KEY', 'chave-gemini')
    chamadas = []

    def _urlopen(req, *args, **kwargs):
        url = req.full_url if hasattr(req, 'full_url') else str(req)
        chamadas.append(url)
        if 'viacep' in url:
            raise urllib.error.URLError('viacep fora do ar')
        return _RespostaFalsa({"candidates": [
            {"content": {"parts": [{"text": '{"bairro": "Centro"}'}]}}]})

    monkeypatch.setattr('urllib.request.urlopen', _urlopen)
    resposta = client.post('/api/ia/sugestao-bairro', headers={'Origin': ORIGEM_LOCAL},
        data=json.dumps({"cep": "01001-000"}), content_type='application/json')

    assert resposta.status_code == 200
    dados = json.loads(resposta.data)
    assert dados['bairro'] == 'Centro'
    assert dados['fonte'] == 'Gemini AI'
    assert any('generativelanguage' in u for u in chamadas)


def test_queda_dos_dois_provedores_devolve_erro(client, urlopen_falso, monkeypatch):
    monkeypatch.setattr(config, 'GEMINI_API_KEY', 'chave-gemini')
    urlopen_falso['resposta'] = urllib.error.URLError('tudo fora do ar')
    resposta = client.post('/api/ia/sugestao-bairro', headers={'Origin': ORIGEM_LOCAL},
        data=json.dumps({"cep": "01001-000"}), content_type='application/json')
    # ViaCEP e Gemini fora do ar: falha de servico externo, 502.
    assert resposta.status_code == 502


# =============================================================================
# Excel / OneDrive
# =============================================================================
def _criar_cliente(client):
    client.post('/api/clientes', headers={'Origin': ORIGEM_LOCAL},
        data=json.dumps({"nome": "Maria Souza", "cep": "12345-678", "rua": "Rua A",
                         "bairro": "Centro", "cidade": "Sao Paulo",
                         "entrega_retirada": "Entrega"}),
        content_type='application/json')
    return json.loads(client.get('/api/clientes').data)[0]['id']


def test_envio_sem_sessao_e_recusado(client):
    resposta = client.post('/api/excel/enviar', headers={'Origin': ORIGEM_LOCAL},
        data=json.dumps({"ids": [1]}), content_type='application/json')
    assert resposta.status_code == 401


def test_envio_sem_ids_e_recusado(client):
    database.salvar_sessao("token-graph", "conta@exemplo.com")
    resposta = client.post('/api/excel/enviar', headers={'Origin': ORIGEM_LOCAL},
        data=json.dumps({"ids": []}), content_type='application/json')
    assert resposta.status_code == 400


def test_envio_com_ids_inexistentes_devolve_404(client):
    database.salvar_sessao("token-graph", "conta@exemplo.com")
    resposta = client.post('/api/excel/enviar', headers={'Origin': ORIGEM_LOCAL},
        data=json.dumps({"ids": [999999]}), content_type='application/json')
    assert resposta.status_code == 404


def test_envio_bem_sucedido(client, urlopen_falso, monkeypatch):
    monkeypatch.setattr('webbrowser.open', lambda _url: None)
    database.salvar_sessao("token-graph", "conta@exemplo.com")
    cliente_id = _criar_cliente(client)
    urlopen_falso['resposta'] = _RespostaFalsa({"webUrl": "https://onedrive/x.xlsx"})

    resposta = client.post('/api/excel/enviar', headers={'Origin': ORIGEM_LOCAL},
        data=json.dumps({"ids": [cliente_id], "nome_arquivo": "Clientes"}),
        content_type='application/json')

    assert resposta.status_code == 200
    assert json.loads(resposta.data)['url'] == "https://onedrive/x.xlsx"
    requisicao = urlopen_falso['requisicoes'][0]
    assert requisicao.get_method() == 'PUT'
    assert 'Clientes.xlsx' in requisicao.full_url


def test_token_expirado_encerra_a_sessao(client, urlopen_falso):
    database.salvar_sessao("token-velho", "conta@exemplo.com")
    cliente_id = _criar_cliente(client)
    urlopen_falso['resposta'] = _erro_http(401, {"error": "InvalidAuthenticationToken"})

    resposta = client.post('/api/excel/enviar', headers={'Origin': ORIGEM_LOCAL},
        data=json.dumps({"ids": [cliente_id]}), content_type='application/json')

    assert resposta.status_code == 401
    assert database.obter_sessao() is None


def test_erro_do_graph_e_reportado(client, urlopen_falso):
    database.salvar_sessao("token", "conta@exemplo.com")
    cliente_id = _criar_cliente(client)
    urlopen_falso['resposta'] = _erro_http(507, {"error": "InsufficientStorage"})
    resposta = client.post('/api/excel/enviar', headers={'Origin': ORIGEM_LOCAL},
        data=json.dumps({"ids": [cliente_id]}), content_type='application/json')
    # Erro devolvido pelo Microsoft Graph: 502, como manda o API_STANDARD.
    assert resposta.status_code == 502


def test_falha_de_conexao_com_o_graph(client, urlopen_falso):
    database.salvar_sessao("token", "conta@exemplo.com")
    cliente_id = _criar_cliente(client)
    urlopen_falso['resposta'] = urllib.error.URLError('sem rota')
    resposta = client.post('/api/excel/enviar', headers={'Origin': ORIGEM_LOCAL},
        data=json.dumps({"ids": [cliente_id]}), content_type='application/json')
    assert resposta.status_code == 502


# =============================================================================
# Relatorios
# =============================================================================








# =============================================================================
# Auth
# =============================================================================
def test_status_sem_sessao(client):
    assert json.loads(client.get('/api/auth/status').data)['logado'] is False


def test_status_com_sessao(client):
    database.salvar_sessao("token", "conta@exemplo.com")
    dados = json.loads(client.get('/api/auth/status').data)
    assert dados['logado'] is True
    assert dados['conta'] == 'conta@exemplo.com'


def test_logout_encerra_a_sessao(client):
    database.salvar_sessao("token", "conta@exemplo.com")
    resposta = client.post('/api/auth/logout', headers={'Origin': ORIGEM_LOCAL})
    assert resposta.status_code == 200
    assert database.obter_sessao() is None


def test_login_abre_o_navegador_com_pkce(client, monkeypatch):
    abertas = []
    monkeypatch.setattr('webbrowser.open', lambda url: abertas.append(url))
    config._oauth_pending.clear()

    resposta = client.get('/api/auth/login')

    assert resposta.status_code == 200
    assert len(abertas) == 1
    assert 'code_challenge_method=S256' in abertas[0]
    assert len(config._oauth_pending) == 1
    estado = next(iter(config._oauth_pending))
    assert 'verifier' in config._oauth_pending[estado]


def test_callback_sem_codigo_e_recusado(client):
    assert client.get('/callback').status_code == 400


def test_callback_com_state_desconhecido_e_recusado(client):
    assert client.get('/callback?code=abc&state=nunca-existiu').status_code == 400


def test_callback_completo_grava_a_sessao(client, monkeypatch):
    config._oauth_pending.clear()
    config._oauth_pending['estado-x'] = {'verifier': 'v', 'ts': 0}

    respostas = [
        _RespostaFalsa({"access_token": "token-novo"}),
        _RespostaFalsa({"userPrincipalName": "maria@exemplo.com"}),
    ]
    monkeypatch.setattr('urllib.request.urlopen', lambda *a, **k: respostas.pop(0))

    resposta = client.get('/callback?code=abc&state=estado-x')

    assert resposta.status_code == 200
    sessao = database.obter_sessao()
    assert sessao['conta'] == 'maria@exemplo.com'
    assert sessao['token'] == 'token-novo'


def test_callback_com_erro_no_token_endpoint(client, monkeypatch):
    config._oauth_pending.clear()
    config._oauth_pending['estado-y'] = {'verifier': 'v', 'ts': 0}

    def _urlopen(*_args, **_kwargs):
        raise _erro_http(400, {"error": "invalid_grant"})

    monkeypatch.setattr('urllib.request.urlopen', _urlopen)
    assert client.get('/callback?code=abc&state=estado-y').status_code == 400
