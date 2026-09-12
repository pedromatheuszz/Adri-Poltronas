"""
Quem pode destravar a base.

Ate a 1.5.0 a resposta era: qualquer conta Microsoft. O guarda de autenticacao
aceitava qualquer linha na tabela `sessao` com token nao vazio, sem olhar de
QUEM era a conta, e o fluxo OAuth usa o endpoint `/common`, que aceita conta
pessoal ou de qualquer tenant.

A explorabilidade sempre foi baixa, e o motivo vale registrar: quem chega a
`/api/auth/login` ja precisa do token de capacidade, que vive em %APPDATA%, e
quem le esse arquivo ja poderia abrir o SQLite direto. Quem protege de fato e a
capacidade -- a autenticacao era decorativa.

O risco e operacional: um colaborador conecta a conta pessoal e passa a ser,
para todos os efeitos do sistema, o mesmo que o dono. Faturar, restaurar backup
e baixar o banco completo tem exatamente a mesma permissao que listar clientes.

Este e o degrau 1 dos tres que a auditoria propoe -- o mais barato, que fecha o
cenario concreto. Os degraus 2 (identidade propria, desacoplada do OneDrive) e
3 (papeis: operacao x administracao) continuam abertos e sao decisao de produto.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

import config  # noqa: E402

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))


@pytest.fixture
def allowlist(monkeypatch):
    """Define a allowlist como se viesse do ambiente."""
    def _definir(*contas):
        conjunto = frozenset(c.strip().casefold() for c in contas if c.strip())
        monkeypatch.setattr(config, 'CONTAS_AUTORIZADAS', conjunto)
    return _definir


# =============================================================================
# A regra
# =============================================================================
def test_sem_allowlist_qualquer_conta_passa(allowlist):
    """
    Vazio significa "qualquer conta", e a escolha e deliberada.

    Ligar a restricao por padrao trancaria o dono fora do proprio aplicativo na
    primeira atualizacao, com a unica saida sendo editar um arquivo de
    configuracao que ele nao sabe que existe. Quem quer a restricao a declara.
    """
    allowlist()
    assert config.conta_autorizada('qualquer@exemplo.com')
    assert config.conta_autorizada('')


def test_conta_na_allowlist_passa(allowlist):
    allowlist('adri@exemplo.com')
    assert config.conta_autorizada('adri@exemplo.com')


def test_conta_fora_da_allowlist_e_recusada(allowlist):
    """O cenario do colaborador que conecta a conta pessoal."""
    allowlist('adri@exemplo.com')
    assert not config.conta_autorizada('colaborador@gmail.com')


def test_a_comparacao_ignora_caixa_e_espaco(allowlist):
    """
    E-mail nao diferencia maiuscula de minuscula. Recusar o dono porque ele
    digitou o proprio e-mail com inicial maiuscula seria um defeito pior do que
    o que a allowlist resolve.
    """
    allowlist('  Adri@Exemplo.COM  ')
    assert config.conta_autorizada('adri@exemplo.com')
    assert config.conta_autorizada('ADRI@EXEMPLO.COM')
    assert config.conta_autorizada(' adri@exemplo.com ')


def test_conta_vazia_e_recusada_quando_ha_allowlist(allowlist):
    """Sessao sem conta gravada nao pode virar coringa."""
    allowlist('adri@exemplo.com')
    assert not config.conta_autorizada('')
    assert not config.conta_autorizada(None)


# =============================================================================
# Como a variavel e lida
# =============================================================================
@pytest.mark.parametrize('bruto, esperado', [
    ('a@x.com', {'a@x.com'}),
    ('a@x.com,b@x.com', {'a@x.com', 'b@x.com'}),
    ('a@x.com; b@x.com', {'a@x.com', 'b@x.com'}),      # ponto e virgula tambem
    ('  A@X.com , , b@x.com  ', {'a@x.com', 'b@x.com'}),  # vazios descartados
    ('', set()),
    ('   ', set()),
])
def test_leitura_da_variavel_de_ambiente(bruto, esperado, monkeypatch):
    """
    O operador vai digitar isso a mao num arquivo de texto. Aceitar virgula e
    ponto e virgula, e tolerar espaco sobrando, custa nada e evita o suporte
    mais chato que existe: "eu configurei e nao funcionou".
    """
    monkeypatch.setenv('ADRI_CONTAS_AUTORIZADAS', bruto)
    import importlib
    recarregado = importlib.reload(config)
    try:
        assert set(recarregado.CONTAS_AUTORIZADAS) == esperado
    finally:
        monkeypatch.delenv('ADRI_CONTAS_AUTORIZADAS', raising=False)
        importlib.reload(config)


# =============================================================================
# A allowlist na borda HTTP
# =============================================================================
# Nao basta `conta_autorizada()` estar certa: ela precisa ser consultada em
# TODO lugar que afirma algo sobre a sessao. `/api/auth/status` esta em
# ROTAS_SEM_AUTH -- precisa estar, porque e ela que a tela consulta para saber
# se ha sessao --, entao o guarda de `/api/` nao roda ali e a checagem tinha de
# ser feita na propria rota.
@pytest.fixture
def cliente_http(tmp_path, monkeypatch):
    import app as app_module
    import database

    monkeypatch.setattr(database, 'DB_PATH', str(tmp_path / 'auth.db'))
    app_module.app.config['TESTING'] = True
    with app_module.app.app_context():
        database.criar_tabela()
    return app_module.app.test_client()


def test_status_nao_diz_conectado_para_conta_fora_da_allowlist(cliente_http, allowlist):
    """
    Antes desta checagem a tela anunciava "Conectado (fulano)" no boot e a
    primeira requisicao de dados recusava aquela mesma conta. O app dizia o
    contrario do que ia fazer.
    """
    import database
    import microsoft

    database.salvar_sessao('token-vivo', 'intruso@exemplo.com',
                           refresh_token='r', expira_em=2 ** 31 - 1)
    allowlist('dona@exemplo.com')

    dados = cliente_http.get('/api/auth/status').get_json()

    assert dados['logado'] is False
    assert dados['motivo'] == 'conta_nao_autorizada'
    # A sessao NAO e apagada aqui: quem apaga e o guarda de `/api/`, e uma rota
    # de consulta nao deveria ter efeito colateral destrutivo.
    assert database.obter_sessao() is not None
    assert microsoft is not None  # import usado pela rota; falha cedo se sumir


def test_status_diz_conectado_para_conta_da_allowlist(cliente_http, allowlist):
    import database

    database.salvar_sessao('token-vivo', 'dona@exemplo.com',
                           refresh_token='r', expira_em=2 ** 31 - 1)
    allowlist('dona@exemplo.com')

    dados = cliente_http.get('/api/auth/status').get_json()

    assert dados['logado'] is True
    assert dados['conta'] == 'dona@exemplo.com'


def test_o_403_da_allowlist_carrega_codigo_legivel_por_maquina():
    """
    403 chega de dois lugares: a capacidade ("Acesso negado.") e a allowlist.
    A tela precisa separar os dois sem comparar prosa em portugues, que muda
    quando alguem reescreve o texto.
    """
    fonte = open(os.path.join(RAIZ, 'backend', 'app.py'), encoding='utf-8').read()
    assert '"codigo": "conta_nao_autorizada"' in fonte

    js = open(os.path.join(RAIZ, 'frontend', 'js', 'app.js'), encoding='utf-8').read()
    assert "codigo === 'conta_nao_autorizada'" in js, (
        "o backend emite o codigo e a tela nao o le -- o operador volta a ver erro generico"
    )
