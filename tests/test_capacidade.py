"""
Capacidade de acesso a API local.

Loopback nao e privado. Qualquer processo da maquina -- e qualquer pagina
aberta no navegador do usuario -- alcanca 127.0.0.1:5000. Ate a versao 1.1 o
que separava o aplicativo de um `curl` era a checagem de Origin/Referer, que
so vale para metodos que alteram estado e que um cliente atravessa
simplesmente NAO enviando esses cabecalhos. Na pratica:

    curl http://127.0.0.1:5000/api/clientes

devolvia a lista inteira de clientes, com nome, endereco e CEP.

Estes testes cobrem as propriedades que sustentam a correcao: que o token e
exigido, que a comparacao nao vaza pelo tempo de resposta, e -- desde a
correcao do fail-open -- que a exigencia NAO cai sozinha quando a variavel de
ambiente nao chega. Ate a 1.3.0 ela caia, e uma falha do Electron em repassar
a variavel abria a API inteira. Desligar hoje exige `ADRI_API_SEM_TOKEN=1`.

O teste do cabecalho no `_exigir_capacidade` roda sobre o app real com
TESTING desligado, porque em modo de teste o guarda e propositalmente
transparente.
"""
import os
import sys

import pytest

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(RAIZ, 'backend'))

import capacidade  # noqa: E402


@pytest.fixture
def com_token(monkeypatch):
    monkeypatch.setenv(capacidade.VARIAVEL_DE_AMBIENTE, 'token-desta-execucao')
    return 'token-desta-execucao'


@pytest.fixture
def perfil_temporario(monkeypatch, tmp_path):
    """
    Redireciona o token de reserva para uma pasta descartavel.

    Sem a variavel de ambiente, `token_esperado()` cai no arquivo do perfil --
    que fica ao lado do banco. Apontar `ADRI_DB_PATH` para `tmp_path` evita
    que a suite crie um `.capacidade` no %APPDATA% de quem roda os testes, e o
    cache precisa ser esvaziado junto porque ele guarda por pasta.
    """
    monkeypatch.setenv('ADRI_DB_PATH', str(tmp_path / 'perfil.db'))
    capacidade._reserva_por_pasta.clear()
    yield tmp_path
    capacidade._reserva_por_pasta.clear()


@pytest.fixture
def sem_token(monkeypatch, perfil_temporario):
    monkeypatch.delenv(capacidade.VARIAVEL_DE_AMBIENTE, raising=False)
    monkeypatch.delenv(capacidade.VARIAVEL_DE_DESLIGAMENTO, raising=False)
    return perfil_temporario


@pytest.fixture
def desligada(monkeypatch):
    monkeypatch.setenv(capacidade.VARIAVEL_DE_DESLIGAMENTO, '1')


# =============================================================================
# Liga e desliga
# =============================================================================
def test_exigencia_continua_ligada_sem_variavel_de_ambiente(sem_token):
    """
    O fail-open que a 1.3.1 fecha.

    Se o Electron falhar em repassar `ADRI_API_TOKEN` ao processo filho -- erro
    de spawn, antivirus, backend orfao de outra execucao -- o servidor subia
    com a API inteira aberta. Agora a ausencia da variavel cai no token do
    perfil, e a exigencia permanece de pe.
    """
    assert capacidade.esta_ativa() is True

    token = capacidade.token_esperado()
    assert len(token) == capacidade.BYTES_DO_TOKEN * 2
    assert capacidade.confere(token) is True
    assert capacidade.confere('chute') is False


def test_token_do_perfil_e_o_mesmo_que_o_electron_leria(sem_token):
    """
    O Electron le `.capacidade` do perfil para montar o cabecalho. O backend
    caindo no MESMO arquivo e o que faz os dois convergirem sem conversarem --
    sem isso, a reserva viraria um token que ninguem apresenta e o app abriria
    uma janela onde nenhuma chamada funciona.
    """
    do_arquivo = capacidade.carregar_ou_criar(capacidade.pasta_do_perfil())
    assert capacidade.token_esperado() == do_arquivo


def test_exigencia_ligada_com_variavel_de_ambiente(com_token):
    assert capacidade.esta_ativa() is True
    assert capacidade.token_esperado() == com_token


def test_variavel_com_espacos_em_branco_cai_no_token_do_perfil(sem_token, monkeypatch):
    """Um `set ADRI_API_TOKEN=` no script de inicializacao deixa a variavel
    definida e vazia. Isso nao pode virar token valido -- a API recusaria tudo
    -- nem liberacao geral, que era o comportamento anterior."""
    monkeypatch.setenv(capacidade.VARIAVEL_DE_AMBIENTE, '   ')
    assert capacidade.esta_ativa() is True
    assert capacidade.token_esperado() == capacidade._token_de_reserva()


def test_desligar_exige_opt_in_por_escrito(desligada):
    """A unica porta de saida, e ela existe para `python backend/servidor.py`
    no terminal. Fora dai, quem a usa esta abrindo a API para qualquer processo
    da maquina."""
    assert capacidade.esta_ativa() is False
    assert capacidade.token_esperado() == ''


# =============================================================================
# A conferencia
# =============================================================================
def test_token_correto_e_aceito(com_token):
    assert capacidade.confere(com_token) is True


def test_token_errado_e_recusado(com_token):
    assert capacidade.confere('outro-token') is False


def test_token_ausente_e_recusado(com_token):
    assert capacidade.confere(None) is False
    assert capacidade.confere('') is False


def test_prefixo_correto_nao_basta(com_token):
    """Guarda contra alguem trocar `hmac.compare_digest` por `startswith` ou
    por uma comparacao frouxa numa refatoracao futura."""
    assert capacidade.confere(com_token[:10]) is False
    assert capacidade.confere(com_token + 'a') is False


def test_nada_e_aceito_quando_a_exigencia_esta_desligada(desligada):
    """Com a exigencia desligada quem decide e o `before_request`, que nem
    chega a chamar `confere`. A funcao em si nunca aprova no vazio -- caso
    contrario, esquecer de definir o token viraria 'tudo liberado' vindo do
    lugar errado."""
    assert capacidade.confere('qualquer-coisa') is False


# =============================================================================
# De onde vem o token
# =============================================================================
class _Mapa(dict):
    """Stand-in para `request.headers` e `request.cookies`."""


def test_cabecalho_e_a_via_principal():
    apresentado = capacidade.apresentado_em(
        _Mapa({capacidade.NOME_DO_HEADER: 'do-header'}),
        _Mapa({capacidade.NOME_DO_COOKIE: 'do-cookie'}),
    )
    assert apresentado == 'do-header'


def test_cookie_cobre_quem_nasce_fora_da_injecao():
    """O Electron carimba o cabecalho na sessao da janela. O cookie existe
    para o Service Worker, que reencaminha um Request ja montado."""
    apresentado = capacidade.apresentado_em(
        _Mapa({}), _Mapa({capacidade.NOME_DO_COOKIE: 'do-cookie'})
    )
    assert apresentado == 'do-cookie'


def test_sem_cabecalho_e_sem_cookie_nao_ha_token():
    assert capacidade.apresentado_em(_Mapa({}), _Mapa({})) is None


# =============================================================================
# O arquivo no perfil do usuario
# =============================================================================
def test_token_e_criado_na_primeira_vez_e_reusado_depois(tmp_path):
    """Persistido, e nao sorteado a cada execucao: quando o Electron morre sem
    levar o Python junto, a proxima abertura precisa reconhecer o backend
    orfao que ficou na porta."""
    pasta = str(tmp_path / "AdriPoltronas")

    primeiro = capacidade.carregar_ou_criar(pasta)
    segundo = capacidade.carregar_ou_criar(pasta)

    assert primeiro == segundo
    assert len(primeiro) == capacidade.BYTES_DO_TOKEN * 2  # hexadecimal
    assert os.path.exists(capacidade.caminho_do_arquivo(pasta))


def test_dois_tokens_gerados_nao_se_repetem():
    assert capacidade.gerar_token() != capacidade.gerar_token()


def test_pasta_sem_permissao_de_escrita_ainda_devolve_token(tmp_path, monkeypatch):
    """Perfil somente-leitura nao pode impedir o app de abrir. O token da
    execucao vale em memoria; so nao sobrevive ao fechamento."""
    def recusa(*_args, **_kwargs):
        raise OSError("perfil somente leitura")

    monkeypatch.setattr(capacidade.os, 'makedirs', recusa)
    token = capacidade.carregar_ou_criar(str(tmp_path / "sem-acesso"))

    assert len(token) == capacidade.BYTES_DO_TOKEN * 2


# =============================================================================
# O guarda, sobre o app de verdade
#
# Com TESTING ligado o guarda e propositalmente transparente -- senao a suite
# inteira precisaria carregar o token. Estes testes o desligam para exercitar
# o caminho que a instalacao empacotada percorre.
# =============================================================================
@pytest.fixture
def cliente_com_guarda_ligado(monkeypatch, tmp_path):
    monkeypatch.setenv('ADRI_DB_PATH', str(tmp_path / 'guarda.db'))
    monkeypatch.setenv(capacidade.VARIAVEL_DE_AMBIENTE, 'token-do-app')

    import app as modulo_app
    import database

    monkeypatch.setattr(database, 'DB_PATH', str(tmp_path / 'guarda.db'))
    database.criar_tabela()

    # Sessao local com cookie para que a requisicao com capacidade atravesse
    # tambem a autenticacao. Sem o token, a recusa deve ocorrer antes dela.
    user_id = database.criar_usuario('operador', 'senha-local-de-teste', 'administrador')
    token_sessao = 'token-de-sessao-local'
    database.salvar_sessao_local(token_sessao, user_id, 'operador', 'administrador')

    modulo_app.app.config['TESTING'] = False
    try:
        with modulo_app.app.test_client() as cliente:
            cliente.set_cookie(database.NOME_COOKIE_SESSAO_LOCAL, token_sessao)
            yield cliente
    finally:
        modulo_app.app.config['TESTING'] = True


def test_api_recusa_quem_nao_apresenta_o_token(cliente_com_guarda_ligado):
    """A regressao que motivou o modulo: a lista de clientes -- nome, endereco
    e CEP -- respondia a qualquer coisa que perguntasse na porta 5000."""
    resposta = cliente_com_guarda_ligado.get('/api/clientes')
    assert resposta.status_code == 403


def test_api_responde_a_quem_apresenta_o_token(cliente_com_guarda_ligado):
    resposta = cliente_com_guarda_ligado.get(
        '/api/clientes', headers={capacidade.NOME_DO_HEADER: 'token-do-app'}
    )
    assert resposta.status_code == 200


def test_sonda_de_identidade_responde_sem_token(cliente_com_guarda_ligado):
    """`/api/health` precisa ser alcancavel justamente para se descobrir SE a
    capacidade em maos serve. Nao devolve dado de negocio."""
    resposta = cliente_com_guarda_ligado.get('/api/health')
    assert resposta.status_code == 200
    assert resposta.get_json()['servico'] == 'adri-poltronas'
    assert resposta.get_json()['capacidade_aceita'] is False


def test_cabecalho_aceito_semeia_o_cookie(cliente_com_guarda_ligado):
    resposta = cliente_com_guarda_ligado.get(
        '/api/clientes', headers={capacidade.NOME_DO_HEADER: 'token-do-app'}
    )
    cookies = resposta.headers.getlist('Set-Cookie')
    assert any(capacidade.NOME_DO_COOKIE in c for c in cookies)
    assert any('HttpOnly' in c and 'SameSite=Strict' in c for c in cookies)


def test_host_forjado_e_recusado(cliente_com_guarda_ligado):
    """DNS rebinding: um dominio do atacante que resolve para 127.0.0.1 faz o
    navegador do usuario emprestar a origem. A lista de origens aceitas era
    derivada do proprio header Host -- comparava a mentira com ela mesma."""
    resposta = cliente_com_guarda_ligado.get(
        '/api/clientes',
        headers={capacidade.NOME_DO_HEADER: 'token-do-app', 'Host': 'mal.exemplo'},
    )
    assert resposta.status_code == 400


@pytest.mark.parametrize(('metodo', 'rota'), [
    ('GET', '/api/auth/local/status'),
    ('GET', '/api/auth/local/me'),
    ('POST', '/api/auth/local/login'),
    ('POST', '/api/auth/local/register'),
    ('POST', '/api/auth/local/setup'),
])
def test_rotas_de_auth_local_tambem_exigem_capacidade(cliente_com_guarda_ligado, metodo, rota):
    resposta = cliente_com_guarda_ligado.open(rota, method=metodo, json={})
    assert resposta.status_code == 403


def test_cadastro_local_recusa_origem_externa(cliente_com_guarda_ligado):
    resposta = cliente_com_guarda_ligado.post(
        '/api/auth/local/register',
        json={'username': 'atacante', 'senha': 'senha-segura'},
        headers={
            capacidade.NOME_DO_HEADER: 'token-do-app',
            'Origin': 'https://site-malicioso.exemplo',
        },
    )
    assert resposta.status_code == 403


# =============================================================================
# Rotas isentas: cada uma tem um motivo, e nenhuma devolve dado de negocio
# =============================================================================
def test_isencoes_sao_apenas_as_duas_necessarias():
    """
    Uma isencao a mais e uma porta aberta.

    Eram tres ate a 1.4.2. O webhook do Asaas saiu com a integracao, e com ele
    o unico caminho pelo qual algo da internet falava com este backend. Restam
    o callback do OAuth, que chega pelo navegador do sistema e nao tem como
    carregar o cabecalho, e a sonda de identidade, que nao devolve dado de
    negocio.
    As rotas de login local tambem exigem capacidade: o Electron a injeta
    antes de carregar a tela de login.
    """
    assert capacidade.ROTAS_ISENTAS == frozenset({
        '/callback',
        '/api/health',
    })
