"""
Testes das integracoes externas: Asaas, Gemini/ViaCEP, Microsoft Graph e a
exportacao de relatorios.

Nenhum teste toca a rede -- `urllib.request.urlopen` e substituido por um duplo
que devolve respostas controladas. Antes destes testes estes eram os modulos
menos cobertos do projeto (asaas 31%, ia 27%, excel 45%), justamente os que
lidam com dinheiro e com o token do OneDrive.
"""
import io
import json
import os
import sys
import tempfile
import urllib.error

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

import asaas  # noqa: E402
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
def test_sem_chave_reporta_nao_configurado(monkeypatch):
    monkeypatch.setattr(config, 'ASAAS_API_KEY', '')
    assert not asaas.esta_configurado()


def test_com_chave_reporta_configurado(monkeypatch):
    monkeypatch.setattr(config, 'ASAAS_API_KEY', '$aact_hmlg_abc')
    assert asaas.esta_configurado()


def test_ambiente_acompanha_a_flag_de_sandbox(monkeypatch):
    monkeypatch.setattr(config, 'ASAAS_SANDBOX', True)
    assert asaas.ambiente() == 'sandbox'
    monkeypatch.setattr(config, 'ASAAS_SANDBOX', False)
    assert asaas.ambiente() == 'producao'


def test_url_base_acompanha_o_ambiente(monkeypatch):
    monkeypatch.setattr(config, 'ASAAS_SANDBOX', True)
    assert 'sandbox' in asaas._base_url()
    monkeypatch.setattr(config, 'ASAAS_SANDBOX', False)
    assert 'sandbox' not in asaas._base_url()


@pytest.mark.parametrize("chave,sandbox,incompativel", [
    ('$aact_prod_xxx', True, True),
    ('$aact_hmlg_xxx', True, False),
    ('$aact_hmlg_xxx', False, True),
    ('$aact_prod_xxx', False, False),
    ('', True, False),
])
def test_deteccao_de_chave_incompativel(monkeypatch, chave, sandbox, incompativel):
    monkeypatch.setattr(config, 'ASAAS_API_KEY', chave)
    monkeypatch.setattr(config, 'ASAAS_SANDBOX', sandbox)
    assert asaas.chave_incompativel_com_ambiente() is incompativel


def test_headers_levam_a_chave_e_o_user_agent(monkeypatch):
    monkeypatch.setattr(config, 'ASAAS_API_KEY', 'chave-x')
    headers = asaas._headers()
    assert headers['access_token'] == 'chave-x'
    assert 'AdriPoltronas' in headers['User-Agent']
    assert headers['Content-Type'] == 'application/json'
    assert 'Content-Type' not in asaas._headers(content_type=False)


# =============================================================================
# Asaas - camada HTTP
# =============================================================================
def test_request_devolve_json_decodificado(urlopen_falso):
    urlopen_falso['resposta'] = _RespostaFalsa({"id": "pay_1"})
    assert asaas._request('POST', '/payments', {"value": 10}) == {"id": "pay_1"}


def test_request_com_corpo_vazio_devolve_dict_vazio(urlopen_falso):
    urlopen_falso['resposta'] = _RespostaFalsa(b'')
    assert asaas._request('POST', '/payments', {"v": 1}) == {}


def test_request_traduz_erro_http_em_dicionario(urlopen_falso):
    urlopen_falso['resposta'] = _erro_http(401, {"errors": [{"description": "chave invalida"}]})
    resultado = asaas._request('POST', '/payments', {"v": 1})
    assert resultado['_erro'] is True
    assert resultado['_status'] == 401
    assert 'errors' in resultado


def test_request_com_erro_http_nao_json(urlopen_falso):
    urlopen_falso['resposta'] = _erro_http(500, b'<html>erro</html>')
    resultado = asaas._request('POST', '/payments', {"v": 1})
    assert resultado['_erro'] is True
    assert '_detalhe' in resultado


def test_request_traduz_falha_de_conexao(urlopen_falso):
    urlopen_falso['resposta'] = urllib.error.URLError('sem rota')
    resultado = asaas._request('POST', '/payments', {"v": 1})
    assert resultado['_erro'] is True


def test_request_get_e_delete(urlopen_falso):
    urlopen_falso['resposta'] = _RespostaFalsa({"ok": 1})
    assert asaas._request_get('/payments/1') == {"ok": 1}
    assert asaas._request_delete('/payments/1') == {"ok": 1}


def test_get_e_delete_traduzem_erro_http(urlopen_falso):
    urlopen_falso['resposta'] = _erro_http(404, {"erro": "nao encontrado"})
    assert asaas._request_get('/payments/1')['_erro'] is True
    assert asaas._request_delete('/payments/1')['_erro'] is True


def test_get_e_delete_traduzem_falha_de_conexao(urlopen_falso):
    urlopen_falso['resposta'] = urllib.error.URLError('sem rota')
    assert asaas._request_get('/x')['_erro'] is True
    assert asaas._request_delete('/x')['_erro'] is True


# =============================================================================
# Asaas - operacoes
# =============================================================================
def test_criar_cliente_devolve_id(urlopen_falso):
    urlopen_falso['resposta'] = _RespostaFalsa({"id": "cus_1", "name": "Maria"})
    assert asaas.criar_cliente("Maria") == {"id": "cus_1", "nome": "Maria"}


def test_criar_cliente_normaliza_documento_e_telefone(urlopen_falso):
    urlopen_falso['resposta'] = _RespostaFalsa({"id": "cus_1", "name": "Maria"})
    asaas.criar_cliente("Maria", cpf_cnpj="123.456.789-00", telefone="(11) 99999-8888",
                        email="m@x.com", cidade="SP", uf="SP", bairro="Centro",
                        rua="Rua A", cep="01001-000")
    corpo = json.loads(urlopen_falso['requisicoes'][0].data)
    assert corpo['cpfCnpj'] == "12345678900"
    assert corpo['mobilePhone'] == "11999998888"
    assert corpo['zipCode'] == "01001000"
    assert corpo['email'] == "m@x.com"


def test_criar_cliente_propaga_erro(urlopen_falso):
    urlopen_falso['resposta'] = _erro_http(400, {"errors": []})
    assert asaas.criar_cliente("Maria")['_erro'] is True


def test_criar_cobranca_pix_monta_o_corpo(urlopen_falso):
    urlopen_falso['resposta'] = _RespostaFalsa({"id": "pay_1"})
    asaas.criar_cobranca_pix("cus_1", 150.456, "2026-09-01", "Poltrona")
    corpo = json.loads(urlopen_falso['requisicoes'][0].data)
    assert corpo['billingType'] == 'PIX'
    assert corpo['value'] == 150.46
    assert corpo['dueDate'] == '2026-09-01'
    assert corpo['description'] == 'Poltrona'


def test_cobranca_sem_descricao_omite_o_campo(urlopen_falso):
    urlopen_falso['resposta'] = _RespostaFalsa({"id": "pay_1"})
    asaas.criar_cobranca_pix("cus_1", 10.0, "2026-09-01")
    assert 'description' not in json.loads(urlopen_falso['requisicoes'][0].data)


def test_criar_cobranca_boleto_monta_o_corpo(urlopen_falso):
    urlopen_falso['resposta'] = _RespostaFalsa({"id": "pay_2"})
    asaas.criar_cobranca_boleto("cus_1", 99.9, "2026-09-01", "Sofa")
    corpo = json.loads(urlopen_falso['requisicoes'][0].data)
    assert corpo['billingType'] == 'BOLETO'
    assert corpo['postalService'] is False


def test_consultas_e_cancelamento(urlopen_falso):
    urlopen_falso['resposta'] = _RespostaFalsa({"status": "RECEIVED"})
    assert asaas.obter_pagamento("pay_1")['status'] == 'RECEIVED'
    assert asaas.obter_status_pagamento("pay_1")['status'] == 'RECEIVED'
    assert asaas.obter_cliente("cus_1")['status'] == 'RECEIVED'
    assert asaas.obter_qr_code_pix("pay_1")['status'] == 'RECEIVED'
    assert asaas.cancelar_pagamento("pay_1")['status'] == 'RECEIVED'


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
def test_relatorio_filtrado_devolve_clientes_e_regioes(client):
    _criar_cliente(client)
    dados = json.loads(client.get('/api/relatorios').data)
    assert dados['total'] == 1
    assert dados['regioes'][0]['cidade'] == 'Sao Paulo'


def test_relatorio_filtra_por_tipo_e_cidade(client):
    _criar_cliente(client)
    assert json.loads(client.get('/api/relatorios?tipo=Retirada').data)['total'] == 0
    assert json.loads(client.get('/api/relatorios?tipo=Entrega').data)['total'] == 1
    assert json.loads(client.get('/api/relatorios?cidade=Rio').data)['total'] == 0


def test_exportacao_csv(client):
    _criar_cliente(client)
    resposta = client.get('/api/relatorios/exportar?formato=csv')
    assert resposta.status_code == 200
    assert 'text/csv' in resposta.headers['Content-Type']
    assert b'Maria Souza' in resposta.data


def test_exportacao_xlsx(client):
    _criar_cliente(client)
    resposta = client.get('/api/relatorios/exportar?formato=xlsx')
    assert resposta.status_code == 200
    assert resposta.data[:2] == b'PK'  # assinatura de arquivo zip/xlsx


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
