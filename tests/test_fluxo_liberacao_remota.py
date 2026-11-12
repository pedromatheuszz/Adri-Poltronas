"""
O ciclo completo da liberacao remota: dev confirma, cliente libera sozinho.

A pergunta que este arquivo responde com codigo e a que o vendedor faz no
telefone: "eu confirmei o pagamento aqui na aba de Desenvolvedor -- quando
o sistema do CLIENTE libera?". A resposta tem de ser: no proximo contato,
que o aplicativo dele faz a cada 30 segundos aberto, ou na proxima
abertura. Nenhuma etapa manual no computador do cliente.

A API central e o UNICO ponto de contato entre as duas maquinas: o
desenvolvedor nao tem como alcancar o banco do cliente, e o cliente nao
tem como receber o token administrativo. O duble aqui reproduz o contrato
do servico real (`licensing-service/app.py`) -- sync cria a licenca em
teste de 30 dias, o comando administrativo muda o estado, a listagem
alimenta o painel.

SO A REDE e substituida: `urlopen` e trocado por um atendente local, e todo
o resto -- construcao de cabecalho com o Bearer do cofre, checagem de HTTPS,
serializacao, normalizacao, cache de 72 horas, os guardas 401/402 -- roda o
codigo de verdade. E o que permite ao teste afirmar duas coisas que um
duble de funcao nao consegue: que o token administrativo realmente VIAJA
na chamada do painel, e que ele NAO VIAJA na sincronizacao do cliente.
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

import app as app_module  # noqa: E402
import capacidade  # noqa: E402
import database  # noqa: E402
import licenca_remota  # noqa: E402

ORIGEM = 'http://localhost'
TOKEN_DE_CAPACIDADE = 'token-do-app-na-liberacao-remota'

# O mesmo comprimento minimo que o servico real exige (40+ caracteres).
TOKEN_ADMIN = 'token-administrativo-falso-com-mais-de-quarenta-caracteres-0001'

CABECALHOS = {capacidade.NOME_DO_HEADER: TOKEN_DE_CAPACIDADE, 'Origin': ORIGEM}


class _RespostaFake:
    """O que o urlopen devolve: status, corpo, e o comportamento de contexto."""

    def __init__(self, corpo, status=200):
        self.status = status
        self._corpo = json.dumps(corpo).encode('utf-8')

    def read(self, *_tamanhos):
        return self._corpo

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class _CentralFake:
    """
    Atendente com o contrato do licensing-service.

    Guarda o estado por license_id como o PostgreSQL real guardaria, e
    registra cada requisicao -- caminho, e se veio com Authorization -- para
    o teste poder afirmar coisas sobre o trafego, nao so sobre o resultado.
    """

    def __init__(self):
        self.licencas = {}
        self.chamadas = []
        self.sem_rede = False

    # --- o que o teste consulta e manipula --------------------------------
    def expirar(self, license_id):
        conta = self.licencas[license_id]
        conta['expira_em'] = (datetime.now(timezone.utc) - timedelta(days=1)).strftime('%Y-%m-%dT%H:%M:%SZ')

    def alterar(self, license_id, acao):
        """O mesmo efeito das acoes do endpoint administrativo real."""
        conta = self.licencas[license_id]
        agora = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        if acao == 'paid':
            conta['estado'] = 'paid'
        elif acao == 'trial_30_days':
            conta['estado'] = 'trial'
            conta['expira_em'] = (datetime.now(timezone.utc) + timedelta(days=30)).strftime('%Y-%m-%dT%H:%M:%SZ')
        elif acao == 'suspend':
            conta['estado'] = 'suspended'
        else:
            raise AssertionError(f'acao desconhecida no duble: {acao}')
        conta['atualizado_em'] = agora
        return self._registro(license_id)

    # --- o contrato de resposta ---------------------------------------------
    def _registro(self, license_id):
        conta = dict(self.licencas[license_id])
        estado = conta['estado']
        if estado == 'trial' and conta['expira_em'] <= datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'):
            estado = 'expired'
        return {
            'license_id': license_id,
            'username': conta['username'],
            'email': conta['email'],
            'estado': estado,
            'inicio_em': conta.get('inicio_em', ''),
            'expira_em': conta['expira_em'],
            'pago_em': conta.get('pago_em', ''),
            'atualizado_em': conta.get('atualizado_em', ''),
        }

    def _admin_autorizado(self, requisicao):
        apresentado = requisicao.get_header('Authorization') or ''
        return apresentado == 'Bearer ' + TOKEN_ADMIN

    def responder(self, requisicao):
        if self.sem_rede:
            from urllib.error import URLError
            raise URLError('sem rede')

        caminho = requisicao.full_url.split('/v1/', 1)[-1] if '/v1/' in requisicao.full_url else ''
        metodo = requisicao.get_method()
        corpo = json.loads(requisicao.data.decode('utf-8')) if requisicao.data else {}

        self.chamadas.append({
            'caminho': '/' + caminho if caminho else requisicao.full_url,
            'metodo': metodo,
            'com_token': bool(requisicao.get_header('Authorization')),
        })

        if caminho == 'licenses/sync':
            return _RespostaFake(self._sync(corpo))
        if caminho == 'admin/verify' and metodo == 'GET':
            if not self._admin_autorizado(requisicao):
                return _RespostaFake({'erro': 'Acesso negado.'}, 401)
            return _RespostaFake({'valid': True})
        if caminho == 'admin/licenses' and metodo == 'GET':
            if not self._admin_autorizado(requisicao):
                return _RespostaFake({'erro': 'Acesso negado.'}, 401)
            return _RespostaFake({'contas': [self._registro(i) for i in self.licencas]})
        if caminho.startswith('admin/licenses/'):
            if not self._admin_autorizado(requisicao):
                return _RespostaFake({'erro': 'Acesso negado.'}, 401)
            license_id = caminho.rsplit('/', 1)[1]
            if license_id not in self.licencas:
                return _RespostaFake({'erro': 'Conta ainda nao sincronizada.'}, 404)
            return _RespostaFake(self.alterar(license_id, corpo.get('acao')))
        raise AssertionError(f'caminho fora do contrato no duble: {caminho}')

    def _sync(self, corpo):
        """Cria na primeira visita e atualiza o cadastro nas seguintes.

        O servico real guarda hash do segredo; o duble guarda o proprio,
        porque aqui o que interessa e o contrato, nao a critografia dele --
        o hash tem teste proprio no servico.
        """
        license_id = corpo['license_id']
        agora = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        if license_id not in self.licencas:
            self.licencas[license_id] = {
                'segredo': corpo['client_secret'],
                'username': corpo['username'],
                'email': corpo['email'],
                'estado': 'trial',
                'inicio_em': agora,
                'expira_em': (datetime.now(timezone.utc) + timedelta(days=30)).strftime('%Y-%m-%dT%H:%M:%SZ'),
                'atualizado_em': agora,
            }
        conta = self.licencas[license_id]
        if conta['segredo'] != corpo['client_secret']:
            return _RespostaFake({'erro': 'Credencial invalida.'}, 403)
        conta['username'] = corpo['username']
        conta['email'] = corpo['email']
        conta['atualizado_em'] = agora
        return self._registro(license_id)


@pytest.fixture
def central(monkeypatch):
    """A API central no ar, e a URL apontando para ela."""
    import segredos

    central = _CentralFake()
    # Valores da máquina que executa a suite não participam deste contrato.
    monkeypatch.setattr(segredos, '_cache', None)
    monkeypatch.setattr(segredos, '_origem_env', set())
    monkeypatch.setenv('ADRI_LICENCA_API_URL', 'https://central.licencas.teste')
    monkeypatch.setenv('ADRI_LICENCA_ADMIN_TOKEN', TOKEN_ADMIN)
    # So a rede e falsificada. Cabecalho, Bearer, checagem de HTTPS e
    # serializacao seguem sendo os de producao.
    monkeypatch.setattr(licenca_remota, 'urlopen',
                        lambda requisicao, timeout=None: central.responder(requisicao))
    return central


@pytest.fixture
def maquinas(monkeypatch, tmp_path):
    """
    O backend com os guardas de verdade e as duas contas: a do cliente e a
    do desenvolvedor. "Maquinas" no plural porque o banco guarda uma sessao
    local por vez -- os papeis se alternam como quem reloga, nao como quem
    esta conectado ao mesmo tempo.
    """
    banco = str(tmp_path / 'liberacao-remota.db')
    monkeypatch.setenv('ADRI_DB_PATH', banco)
    monkeypatch.setenv(capacidade.VARIAVEL_DE_AMBIENTE, TOKEN_DE_CAPACIDADE)
    monkeypatch.delenv(capacidade.VARIAVEL_DE_DESLIGAMENTO, raising=False)
    monkeypatch.setattr(database, 'DB_PATH', banco)
    database.criar_tabela()

    # O vinculo do desenvolvedor ao computador (identidade Windows + IP
    # publico consultado no ipify + cofre DPAPI) tem os proprios testes em
    # test_autenticacao.py. Aqui ele e dado como conferido: o que este arquivo
    # mede e o ciclo da licenca, e deixa-lo ligado fazia o resultado depender
    # do cofre real e do IP de quem roda a suite.
    from blueprints import auth_local
    monkeypatch.setattr(
        auth_local, '_autorizar_dispositivo_desenvolvedor',
        lambda *_args, **_kwargs: True)

    cliente_id = database.criar_usuario(
        'operador', 'senha-de-teste', 'usuario', 'operador@exemplo.local')
    dev_id = database.criar_usuario(
        'desenvolvedor', 'senha-de-teste', 'desenvolvedor', 'dev@exemplo.local')

    app_module.app.config['TESTING'] = False
    try:
        with app_module.app.test_client() as cliente_http:
            yield {'cliente': cliente_id, 'dev': dev_id, 'http': cliente_http}
    finally:
        app_module.app.config['TESTING'] = True


def _entrar(maquinas, papel):
    """Efetiva o login de uma das duas contas, como as rotas de auth fariam."""
    id_por_papel = {'cliente': (maquinas['cliente'], 'operador', 'usuario'),
                    'dev': (maquinas['dev'], 'desenvolvedor', 'desenvolvedor')}
    user_id, username, role = id_por_papel[papel]
    token = f'token-local-{papel}'
    database.salvar_sessao_local(token, user_id, username, role)
    maquinas['http'].set_cookie(database.NOME_COOKIE_SESSAO_LOCAL, token)
    return user_id


def _license_id_do_cliente(maquinas):
    conta = database.obter_identidade_licenca_remota(maquinas['cliente'])
    assert conta, 'o cliente deveria ter identidade remota apos sincronizar'
    return conta['licenca_remota_id']


def _bloquear_o_cliente_no_central(central, maquinas):
    """Sincroniza, vence o teste centralmente e deixa o cliente sabendo disso.

    A segunda consulta de status e de proposito: e a enquete de 30 segundos
    que o app aberto faz, e e ela que atualiza o cache local. Sem ela o
    guarda leria o cache antigo -- no mundo real essa enquete acontece
    sozinha antes de qualquer outra requisicao de negocio.
    """
    _entrar(maquinas, 'cliente')
    resposta = maquinas['http'].get('/api/licenca/status', headers=CABECALHOS)
    assert resposta.status_code == 200
    central.expirar(_license_id_do_cliente(maquinas))
    vencida = maquinas['http'].get('/api/licenca/status', headers=CABECALHOS)
    assert vencida.get_json()['estado'] == 'expirada'

    bloqueio = maquinas['http'].get('/api/clientes', headers=CABECALHOS)
    assert bloqueio.status_code == 402, 'o bloqueio deveria comecar expirado'
    # A recusa diz de onde veio: o cliente e a pessoa certa de saber que
    # quem mandou bloquear foi o servidor central, e nao o relogio local.
    assert bloqueio.get_json()['licenca']['origem'] == 'central'


# =============================================================================
# O painel enxerga o cliente
# =============================================================================
def test_o_cliente_aparece_no_painel_apos_a_primeira_sincronizacao(central, maquinas):
    _entrar(maquinas, 'cliente')
    status = maquinas['http'].get('/api/licenca/status', headers=CABECALHOS)

    assert status.status_code == 200
    assert status.get_json()['estado'] == 'teste'
    # A primeira visita do computador do cliente e o que registra a conta.
    assert len(central.licencas) == 1

    _entrar(maquinas, 'dev')
    resposta = maquinas['http'].get('/api/licenca/remota/contas', headers=CABECALHOS)

    assert resposta.status_code == 200
    contas = resposta.get_json()['contas']
    assert [c['username'] for c in contas] == ['operador']
    assert contas[0]['estado'] == 'trial'


def test_a_sincronizacao_do_cliente_nao_carrega_o_token_administrativo(central, maquinas):
    """
    O contrato de seguranca da ponta cliente: o computador do cliente NUNCA
    precisa do token administrativo -- quem o tiver lista e controla TODAS
    as licencas. Se a sincronizacao passasse a exigi-lo, cada instalacao de
    cliente viraria uma instalacao de administrador.
    """
    _entrar(maquinas, 'cliente')
    maquinas['http'].get('/api/licenca/status', headers=CABECALHOS)
    _entrar(maquinas, 'dev')
    maquinas['http'].get('/api/licenca/remota/contas', headers=CABECALHOS)

    syncs = [c for c in central.chamadas if c['caminho'].endswith('licenses/sync')]
    admin = [c for c in central.chamadas if '/admin/' in c['caminho']]

    assert syncs, 'nenhuma sincronizacao chegou ao central'
    assert all(not c['com_token'] for c in syncs), 'sync levou Authorization'
    assert all(c['com_token'] for c in admin), 'chamada admin sem Bearer'


def test_o_painel_exige_o_token_administrativo_na_apelacao(central, maquinas, monkeypatch):
    """
    Sem o token na maquina, o painel NAO lista: a API central recusa e a
    rota traduz. E o que permite configurar o cliente com somente a URL.
    """
    from urllib.error import HTTPError

    _entrar(maquinas, 'dev')

    def _sem_token(_requisicao, timeout=None):
        raise HTTPError('url', 401, 'Acesso negado.', None, None)

    monkeypatch.setattr(licenca_remota, 'urlopen', _sem_token)
    resposta = maquinas['http'].get('/api/licenca/remota/contas', headers=CABECALHOS)

    assert resposta.status_code == 503
    assert 'recusou' in resposta.get_json()['erro']


# =============================================================================
# A liberacao: o ciclo que o vendedor executa no telefone
# =============================================================================
def test_confirmar_pagamento_libera_o_cliente_no_proximo_contato(central, maquinas):
    """
    O cenario inteiro, na ordem em que ele acontece de verdade:

    1. o teste do cliente vence no servidor central, e o computador dele
       passa a receber 402;
    2. o desenvolvedor confirma o pagamento na aba de Desenvolvedor;
    3. o proximo contato do cliente -- sem nenhuma acao manual nele --
       devolve `paga`, e a API volta a responder.

    Entre 2 e 3 ha no maximo 30 segundos com o app aberto, ou a proxima
    abertura com ele fechado. Nada mais.
    """
    _bloquear_o_cliente_no_central(central, maquinas)

    _entrar(maquinas, 'dev')
    acao = maquinas['http'].post(
        '/api/licenca/remota/contas/' + _license_id_do_cliente(maquinas),
        json={'acao': 'paid'}, headers=CABECALHOS)
    assert acao.status_code == 200
    assert acao.get_json()['estado'] == 'paid'

    # A confirmacao mora no servidor central; a maquina do cliente so faz
    # a pergunta de sempre.
    _entrar(maquinas, 'cliente')
    status = maquinas['http'].get('/api/licenca/status', headers=CABECALHOS)
    assert status.get_json()['estado'] == 'paga'

    resposta = maquinas['http'].get('/api/clientes', headers=CABECALHOS)
    assert resposta.status_code == 200


def test_liberar_mais_30_dias_pelo_painel_estende_o_cliente(central, maquinas):
    _bloquear_o_cliente_no_central(central, maquinas)

    _entrar(maquinas, 'dev')
    acao = maquinas['http'].post(
        '/api/licenca/remota/contas/' + _license_id_do_cliente(maquinas),
        json={'acao': 'trial_30_days'}, headers=CABECALHOS)
    assert acao.status_code == 200

    _entrar(maquinas, 'cliente')
    status = maquinas['http'].get('/api/licenca/status', headers=CABECALHOS)
    situacao = status.get_json()
    assert situacao['estado'] == 'teste'
    assert situacao['dias_restantes'] >= 29

    assert maquinas['http'].get('/api/clientes', headers=CABECALHOS).status_code == 200


def test_suspender_pelo_painel_bloqueia_o_cliente(central, maquinas):
    """Suspensao e o caminho de volta de um pagamento contestado."""
    _entrar(maquinas, 'cliente')
    maquinas['http'].get('/api/licenca/status', headers=CABECALHOS)

    _entrar(maquinas, 'dev')
    acao = maquinas['http'].post(
        '/api/licenca/remota/contas/' + _license_id_do_cliente(maquinas),
        json={'acao': 'suspend'}, headers=CABECALHOS)
    assert acao.status_code == 200

    _entrar(maquinas, 'cliente')
    status = maquinas['http'].get('/api/licenca/status', headers=CABECALHOS)
    assert status.get_json()['estado'] == 'expirada'
    assert maquinas['http'].get('/api/clientes', headers=CABECALHOS).status_code == 402


def test_cliente_sem_rede_liberacao_chega_na_proxima_janela(central, maquinas):
    """
    O desenvolvedor confirma enquanto o cliente esta fora do ar. O cliente
    continua bloqueado -- o cache local ainda diz expirado, e mentir
    "liberado" ate a confirmacao voltar seria inverter a confianca -- e a
    liberacao chega no primeiro contato apos a rede voltar, sem relogio
    nem acao manual.
    """
    _bloquear_o_cliente_no_central(central, maquinas)

    # O desenvolvedor confirmou; so que o computador do cliente esta sem rede.
    _entrar(maquinas, 'dev')
    maquinas['http'].post(
        '/api/licenca/remota/contas/' + _license_id_do_cliente(maquinas),
        json={'acao': 'paid'}, headers=CABECALHOS)

    central.sem_rede = True
    _entrar(maquinas, 'cliente')
    status_off = maquinas['http'].get('/api/licenca/status', headers=CABECALHOS)
    assert status_off.get_json()['estado'] == 'expirada'
    assert maquinas['http'].get('/api/clientes', headers=CABECALHOS).status_code == 402

    central.sem_rede = False
    status_on = maquinas['http'].get('/api/licenca/status', headers=CABECALHOS)
    assert status_on.get_json()['estado'] == 'paga'
    assert maquinas['http'].get('/api/clientes', headers=CABECALHOS).status_code == 200
