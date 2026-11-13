"""
As rotas de conta local, exercitadas de ponta a ponta com os guardas ligados.

Os outros arquivos semeiam a sessao direto no banco para chegar ao que querem
medir, e com isso o caminho que o operador de fato percorre -- digitar usuario
e senha, criar conta, trocar a senha -- ficava sem teste nenhum. O mesmo valia
para a gestao de contas do desenvolvedor e para o vinculo dele ao computador,
que e a regra mais intrincada do modulo.

Aqui tudo passa pelas rotas: o cookie de sessao e o que o servidor devolve no
login, e nao um valor plantado.
"""
import os
import sys

import pytest

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(RAIZ, 'backend'))

import capacidade  # noqa: E402

TOKEN_DE_CAPACIDADE = 'token-do-app-nas-rotas-de-conta'
CABECALHOS = {capacidade.NOME_DO_HEADER: TOKEN_DE_CAPACIDADE}
SENHA = 'senha-local-de-teste'
OUTRA_SENHA = 'outra-senha-bem-comprida'
TOKEN_ADMIN = 'x' * 48
IDENTIDADE = 'a' * 64
IP = '203.0.113.10'


@pytest.fixture
def ambiente(monkeypatch, tmp_path):
    """O app com os guardas ligados, sobre banco e cofre descartaveis."""
    banco = str(tmp_path / 'contas.db')
    monkeypatch.setenv('ADRI_DB_PATH', banco)
    monkeypatch.setenv('APPDATA', str(tmp_path / 'appdata'))
    monkeypatch.setenv(capacidade.VARIAVEL_DE_AMBIENTE, TOKEN_DE_CAPACIDADE)
    monkeypatch.delenv(capacidade.VARIAVEL_DE_DESLIGAMENTO, raising=False)

    import app as modulo_app
    import database
    import licenca_remota
    import limites
    import segredos
    from blueprints import auth_local

    # A licenca central nao e o assunto: sem ela vale o teste local da conta.
    monkeypatch.setattr(licenca_remota, 'api_configurada', lambda: False)
    monkeypatch.setattr(licenca_remota, 'identidade_instalacao', lambda: IDENTIDADE)
    monkeypatch.setattr(segredos, '_cache', {})
    monkeypatch.setattr(segredos, '_origem_env', set())
    # O resultado do vinculo de dispositivo fica em cache de modulo por 30 s.
    monkeypatch.setattr(auth_local, '_dispositivo_validado_ate', 0.0)
    monkeypatch.setattr(auth_local, '_dispositivo_validado', False)
    monkeypatch.setattr(auth_local, '_ip_publico_atual', lambda: IP)
    # Os limites por minuto tem teste proprio; aqui uma dezena de logins no
    # mesmo segundo e o cenario, nao um abuso.
    monkeypatch.setattr(limites.limiter, 'enabled', False)

    monkeypatch.setattr(database, 'DB_PATH', banco)
    database.criar_tabela()

    modulo_app.app.config['TESTING'] = False
    try:
        yield {'app': modulo_app.app, 'database': database, 'auth_local': auth_local,
               'segredos': segredos, 'licenca_remota': licenca_remota}
    finally:
        modulo_app.app.config['TESTING'] = True


@pytest.fixture
def http(ambiente):
    with ambiente['app'].test_client() as cliente:
        yield cliente


def _post(http, rota, corpo=None, **extra):
    return http.post('/api/auth/local' + rota, json=corpo, headers=CABECALHOS, **extra)


def _entrar(http, username, senha=SENHA):
    return _post(http, '/login', {'username': username, 'senha': senha})


def _eu(http):
    return http.get('/api/auth/local/me', headers=CABECALHOS)


def _abriu_sessao(resposta) -> bool:
    """A resposta trouxe o cookie de SESSAO? (O de capacidade vem sempre.)"""
    return any(cookie.startswith('adri_sessao_local=')
               for cookie in resposta.headers.getlist('Set-Cookie'))


# =============================================================================
# Login
# =============================================================================
def test_login_com_senha_certa_abre_a_sessao(ambiente, http):
    ambiente['database'].criar_usuario('operador', SENHA, 'usuario', 'op@exemplo.local')

    resposta = _entrar(http, 'operador')

    assert resposta.status_code == 200
    assert resposta.get_json()['usuario']['role'] == 'usuario'
    # Cookie que script nenhum le e que outra origem nao consegue provocar.
    assert _abriu_sessao(resposta)
    cookie = next(c for c in resposta.headers.getlist('Set-Cookie')
                  if c.startswith('adri_sessao_local='))
    assert 'HttpOnly' in cookie and 'SameSite=Strict' in cookie
    # A senha e o hash nunca voltam na resposta.
    assert SENHA not in resposta.get_data(as_text=True)
    assert 'password_hash' not in resposta.get_data(as_text=True)

    assert _eu(http).get_json()['usuario']['username'] == 'operador'
    assert http.get('/api/clientes', headers=CABECALHOS).status_code == 200


def test_login_com_senha_errada_nao_abre_nada(ambiente, http):
    ambiente['database'].criar_usuario('operador', SENHA)

    resposta = _entrar(http, 'operador', 'senha-errada-qualquer')

    assert resposta.status_code == 401
    assert not _abriu_sessao(resposta)
    assert _eu(http).status_code == 401
    assert http.get('/api/clientes', headers=CABECALHOS).status_code == 401


def test_usuario_inexistente_e_senha_errada_dao_a_mesma_resposta(ambiente, http):
    """Mensagens diferentes diriam a quem tenta quais nomes existem."""
    ambiente['database'].criar_usuario('operador', SENHA)

    errada = _entrar(http, 'operador', 'senha-errada-qualquer')
    inexistente = _entrar(http, 'ninguem', 'senha-errada-qualquer')

    assert errada.status_code == inexistente.status_code == 401
    assert errada.get_json() == inexistente.get_json()


def test_conta_desativada_nao_entra(ambiente, http):
    user_id = ambiente['database'].criar_usuario('operador', SENHA)
    ambiente['database'].atualizar_usuario_local(user_id, ativo=0)

    assert _entrar(http, 'operador').status_code == 401


@pytest.mark.parametrize('corpo', [
    None,
    [],
    {'username': 'operador'},
    {'username': 'operador', 'senha': ''},
    {'username': '', 'senha': SENHA},
    {'username': 123, 'senha': SENHA},
    {'username': 'operador', 'senha': ['lista']},
    {'username': 'x' * 81, 'senha': SENHA},
])
def test_login_malformado_e_400_e_nao_500(http, corpo):
    assert _post(http, '/login', corpo).status_code == 400


def test_logout_encerra_a_sessao(ambiente, http):
    ambiente['database'].criar_usuario('operador', SENHA)
    _entrar(http, 'operador')

    assert _post(http, '/logout').status_code == 200
    assert _eu(http).status_code == 401
    assert http.get('/api/clientes', headers=CABECALHOS).status_code == 401
    # Sair duas vezes nao e erro de servidor.
    assert _post(http, '/logout').status_code == 401


def test_novo_login_invalida_o_cookie_anterior(ambiente):
    """Uma sessao por vez: o cookie de quem entrou antes deixa de valer."""
    ambiente['database'].criar_usuario('operador', SENHA)
    primeiro = ambiente['app'].test_client()
    segundo = ambiente['app'].test_client()
    _entrar(primeiro, 'operador')
    _entrar(segundo, 'operador')

    assert _eu(segundo).status_code == 200
    assert _eu(primeiro).status_code == 401


def test_status_diz_se_ha_contas_sem_exigir_sessao(ambiente, http):
    antes = http.get('/api/auth/local/status', headers=CABECALHOS).get_json()
    ambiente['database'].criar_usuario('operador', SENHA)
    depois = http.get('/api/auth/local/status', headers=CABECALHOS).get_json()

    assert antes['tem_usuarios'] is False and depois['tem_usuarios'] is True
    # Sem a chave do fornecedor no cofre, a instalacao nao oferece o cadastro
    # de desenvolvedor -- e o caso de toda maquina de cliente.
    assert antes['setup_required'] is False


# =============================================================================
# Cadastro publico
# =============================================================================
def test_cadastro_cria_conta_comum_e_ja_entra(http):
    resposta = _post(http, '/register', {'username': 'nova', 'senha': SENHA, 'email': 'n@exemplo.local'})

    assert resposta.status_code == 201
    assert resposta.get_json()['usuario']['role'] == 'usuario'
    assert _eu(http).get_json()['usuario']['username'] == 'nova'


@pytest.mark.parametrize('role', ['administrador', 'desenvolvedor'])
def test_cadastro_publico_nao_cria_perfil_administrativo(ambiente, http, role):
    """A tela de login e alcancavel por quem estiver na frente do computador."""
    resposta = _post(http, '/register', {'username': 'esperto', 'senha': SENHA,
                                         'email': '', 'role': role})

    assert resposta.status_code == 403
    assert ambiente['database'].obter_usuario_por_username('esperto') is None


def test_cadastro_recusa_nome_repetido(ambiente, http):
    ambiente['database'].criar_usuario('operador', SENHA)

    resposta = _post(http, '/register', {'username': 'operador', 'senha': SENHA, 'email': ''})

    assert resposta.status_code == 409


@pytest.mark.parametrize('corpo', [
    None,
    {'username': 'nova', 'senha': 'curta', 'email': ''},
    {'username': 'nova', 'senha': 'é' * 40, 'email': ''},          # passa de 72 bytes
    {'username': '', 'senha': SENHA, 'email': ''},
    {'username': 'x' * 81, 'senha': SENHA, 'email': ''},
    {'username': 'nova', 'senha': SENHA, 'email': 'e' * 255},
    {'username': 'nova', 'senha': SENHA, 'email': '', 'role': 'dono'},
    {'username': 'nova', 'senha': SENHA, 'email': None},
])
def test_cadastro_malformado_e_recusado(ambiente, http, corpo):
    assert _post(http, '/register', corpo).status_code == 400
    assert ambiente['database'].obter_usuario_por_username('nova') is None


# =============================================================================
# Troca de senha
# =============================================================================
def test_trocar_a_senha_exige_a_atual_e_passa_a_valer(ambiente, http):
    ambiente['database'].criar_usuario('operador', SENHA)
    _entrar(http, 'operador')

    recusada = _post(http, '/alterar-senha', {'senha_atual': 'nao-e-esta-senha', 'nova_senha': OUTRA_SENHA})
    aceita = _post(http, '/alterar-senha', {'senha_atual': SENHA, 'nova_senha': OUTRA_SENHA})

    assert recusada.status_code == 400
    assert aceita.status_code == 200
    # A sessao segue aberta, com um cookie novo.
    assert _eu(http).status_code == 200
    with ambiente['app'].test_client() as outro:
        assert _entrar(outro, 'operador', SENHA).status_code == 401
        assert _entrar(outro, 'operador', OUTRA_SENHA).status_code == 200


@pytest.mark.parametrize('corpo', [
    None,
    {'senha_atual': SENHA},
    {'senha_atual': SENHA, 'nova_senha': 'curta'},
    {'senha_atual': SENHA, 'nova_senha': 123},
])
def test_troca_de_senha_malformada_nao_altera_nada(ambiente, http, corpo):
    ambiente['database'].criar_usuario('operador', SENHA)
    _entrar(http, 'operador')

    assert _post(http, '/alterar-senha', corpo).status_code == 400
    with ambiente['app'].test_client() as outro:
        assert _entrar(outro, 'operador', SENHA).status_code == 200


def test_trocar_a_senha_sem_sessao_e_recusado(http):
    resposta = _post(http, '/alterar-senha', {'senha_atual': SENHA, 'nova_senha': OUTRA_SENHA})
    assert resposta.status_code == 401


# =============================================================================
# Gestao de contas, pelo desenvolvedor
# =============================================================================
@pytest.fixture
def dev(ambiente, http, monkeypatch):
    """Desenvolvedor com a sessao aberta, no computador autorizado."""
    monkeypatch.setattr(ambiente['auth_local'], '_autorizar_dispositivo_desenvolvedor',
                        lambda *_args, **_kwargs: True)
    dev_id = ambiente['database'].criar_usuario('dev', SENHA, 'desenvolvedor')
    assert _entrar(http, 'dev').status_code == 200
    return dev_id


def test_desenvolvedor_cria_conta_sem_perder_a_propria_sessao(ambiente, http, dev):
    resposta = _post(http, '/usuarios', {'username': 'gerente', 'senha': SENHA,
                                         'email': 'g@exemplo.local', 'role': 'administrador'})

    assert resposta.status_code == 201
    assert resposta.get_json()['logado'] is False
    assert _eu(http).get_json()['usuario']['username'] == 'dev'
    assert ambiente['database'].obter_usuario_por_username('gerente')['role'] == 'administrador'


@pytest.mark.parametrize('corpo,status', [
    (None, 400),
    ({'username': 'x', 'senha': SENHA, 'email': '', 'role': 'desenvolvedor'}, 400),
    ({'username': 'x', 'senha': 'curta', 'email': '', 'role': 'usuario'}, 400),
    ({'username': '', 'senha': SENHA, 'email': '', 'role': 'usuario'}, 400),
    ({'username': 'x' * 81, 'senha': SENHA, 'email': '', 'role': 'usuario'}, 400),
    ({'username': 'x', 'senha': SENHA, 'email': 'e' * 255, 'role': 'usuario'}, 400),
    ({'username': 'x', 'senha': SENHA, 'email': 5, 'role': 'usuario'}, 400),
    ({'username': 'dev', 'senha': SENHA, 'email': '', 'role': 'usuario'}, 409),
])
def test_criacao_de_conta_invalida_e_recusada(http, dev, corpo, status):
    assert _post(http, '/usuarios', corpo).status_code == status


def test_conta_comum_nao_administra_contas(ambiente, http):
    alvo = ambiente['database'].criar_usuario('alvo', SENHA)
    ambiente['database'].criar_usuario('operador', SENHA)
    _entrar(http, 'operador')

    assert _post(http, '/usuarios', {'username': 'x', 'senha': SENHA, 'email': ''}).status_code == 403
    assert http.get('/api/auth/local/usuarios', headers=CABECALHOS).status_code == 403
    assert http.put(f'/api/auth/local/usuarios/{alvo}', json={'ativo': False},
                    headers=CABECALHOS).status_code == 403
    assert http.delete(f'/api/auth/local/usuarios/{alvo}', headers=CABECALHOS).status_code == 403
    assert _post(http, f'/usuarios/{alvo}/teste', {'acao': 'desativar'}).status_code == 403
    assert ambiente['database'].obter_usuario_por_id(alvo)['ativo'] == 1


def test_desenvolvedor_lista_as_contas_sem_o_hash_da_senha(ambiente, http, dev):
    ambiente['database'].criar_usuario('operador', SENHA)

    resposta = http.get('/api/auth/local/usuarios', headers=CABECALHOS)

    assert resposta.status_code == 200
    assert {u['username'] for u in resposta.get_json()} == {'dev', 'operador'}
    assert 'password_hash' not in resposta.get_data(as_text=True)
    assert all('teste' in u for u in resposta.get_json())


def _alterar(http, user_id, corpo):
    return http.put(f'/api/auth/local/usuarios/{user_id}', json=corpo, headers=CABECALHOS)


def test_desenvolvedor_altera_nome_perfil_acesso_e_senha(ambiente, http, dev):
    alvo = ambiente['database'].criar_usuario('operador', SENHA)

    resposta = _alterar(http, alvo, {'username': 'atendente', 'email': 'a@exemplo.local',
                                     'role': 'administrador', 'senha': OUTRA_SENHA})

    assert resposta.status_code == 200
    conta = ambiente['database'].obter_usuario_por_id(alvo)
    assert (conta['username'], conta['role'], conta['email']) == (
        'atendente', 'administrador', 'a@exemplo.local')
    with ambiente['app'].test_client() as outro:
        assert _entrar(outro, 'atendente', OUTRA_SENHA).status_code == 200


def test_conta_desativada_pelo_desenvolvedor_perde_o_acesso(ambiente, http, dev):
    alvo = ambiente['database'].criar_usuario('operador', SENHA)

    assert _alterar(http, alvo, {'ativo': False}).status_code == 200
    with ambiente['app'].test_client() as outro:
        assert _entrar(outro, 'operador').status_code == 401


@pytest.mark.parametrize('corpo,status', [
    (None, 400),
    ({}, 400),
    ({'username': ''}, 400),
    ({'username': 7}, 400),
    ({'username': 'x' * 81}, 400),
    ({'email': 'e' * 255}, 400),
    ({'role': 'dono'}, 400),
    ({'ativo': 'sim'}, 400),
    ({'senha': 'curta'}, 400),
    # Ja existe um desenvolvedor: o perfil nao e concedido por esta rota.
    ({'role': 'desenvolvedor'}, 409),
    ({'username': 'dev'}, 409),
])
def test_alteracao_invalida_de_conta_e_recusada(ambiente, http, dev, corpo, status):
    alvo = ambiente['database'].criar_usuario('operador', SENHA)

    assert _alterar(http, alvo, corpo).status_code == status
    conta = ambiente['database'].obter_usuario_por_id(alvo)
    assert (conta['username'], conta['role'], conta['ativo']) == ('operador', 'usuario', 1)


@pytest.mark.parametrize('corpo', [
    {'username': 'outro-nome'},
    {'senha': OUTRA_SENHA},
    {'role': 'usuario'},
    {'ativo': False},
])
def test_desenvolvedor_nao_remove_o_proprio_acesso(ambiente, http, dev, corpo):
    """Um clique errado nao pode deixar a instalacao sem quem a administre."""
    assert _alterar(http, dev, corpo).status_code == 400
    conta = ambiente['database'].obter_usuario_por_id(dev)
    assert (conta['username'], conta['role'], conta['ativo']) == ('dev', 'desenvolvedor', 1)


def test_alterar_conta_inexistente_e_404(http, dev):
    assert _alterar(http, 9999, {'email': 'x@exemplo.local'}).status_code == 404


def test_desenvolvedor_exclui_conta_e_ela_nao_entra_mais(ambiente, http, dev):
    alvo = ambiente['database'].criar_usuario('operador', SENHA)

    resposta = http.delete(f'/api/auth/local/usuarios/{alvo}', headers=CABECALHOS)

    assert resposta.status_code == 200
    with ambiente['app'].test_client() as outro:
        assert _entrar(outro, 'operador').status_code == 401
    assert http.delete(f'/api/auth/local/usuarios/{alvo}', headers=CABECALHOS).status_code == 404


def test_desenvolvedor_nao_exclui_a_si_mesmo(ambiente, http, dev):
    assert http.delete(f'/api/auth/local/usuarios/{dev}', headers=CABECALHOS).status_code == 400
    assert ambiente['database'].obter_usuario_por_id(dev) is not None


@pytest.mark.parametrize('corpo,status', [
    (None, 400),
    ({'acao': 7}, 400),
    ({'acao': 'inventada'}, 400),
])
def test_controle_de_teste_recusa_acao_invalida(ambiente, http, dev, corpo, status):
    alvo = ambiente['database'].criar_usuario('operador', SENHA)
    assert _post(http, f'/usuarios/{alvo}/teste', corpo).status_code == status


def test_controle_de_teste_de_conta_inexistente_ou_do_desenvolvedor(http, dev):
    assert _post(http, '/usuarios/9999/teste', {'acao': 'desativar'}).status_code == 404
    assert _post(http, f'/usuarios/{dev}/teste', {'acao': 'desativar'}).status_code == 400


# =============================================================================
# O vinculo do desenvolvedor ao computador
#
# O perfil de desenvolvedor controla licencas de todos os clientes. A regra:
# identidade deste Windows + chave do fornecedor validada na API central; um
# IP publico novo so entra na lista depois de revalidar a chave.
# =============================================================================
@pytest.fixture
def vinculo(ambiente, monkeypatch):
    """Acesso direto a funcao, com a API central sob controle do teste."""
    consultas = []

    def central(token):
        consultas.append(token)
        return central.aceita and token == TOKEN_ADMIN

    central.aceita = True
    monkeypatch.setattr(ambiente['licenca_remota'], 'validar_token_admin', central)
    return {'autorizar': ambiente['auth_local']._autorizar_dispositivo_desenvolvedor,
            'modulo': ambiente['auth_local'], 'segredos': ambiente['segredos'],
            'central': central, 'consultas': consultas}


def _cofre(vinculo, nome):
    return vinculo['segredos'].obter_do_cofre(nome)


def _esquecer_cache(vinculo, monkeypatch):
    monkeypatch.setattr(vinculo['modulo'], '_dispositivo_validado_ate', 0.0)


def test_primeiro_vinculo_exige_a_chave_do_fornecedor(vinculo):
    assert vinculo['autorizar']() is False, 'sem chave no cofre nao ha vinculo'
    assert _cofre(vinculo, 'ADRI_DESENVOLVEDOR_DISPOSITIVO') == ''


def test_primeiro_vinculo_grava_a_identidade_e_o_ip(vinculo):
    assert vinculo['autorizar'](TOKEN_ADMIN) is True

    assert _cofre(vinculo, 'ADRI_DESENVOLVEDOR_DISPOSITIVO') == IDENTIDADE
    assert _cofre(vinculo, 'ADRI_DESENVOLVEDOR_IPS') == IP
    assert vinculo['consultas'] == [TOKEN_ADMIN]


def test_chave_que_a_central_recusa_nao_vincula(vinculo):
    vinculo['central'].aceita = False

    assert vinculo['autorizar'](TOKEN_ADMIN) is False
    assert _cofre(vinculo, 'ADRI_DESENVOLVEDOR_DISPOSITIVO') == ''


def test_chave_curta_nem_chega_a_central(vinculo):
    assert vinculo['autorizar']('curta') is False
    assert vinculo['consultas'] == []


def test_variavel_de_ambiente_nao_simula_o_vinculo(vinculo, monkeypatch):
    """O marcador so vale lido do cofre DPAPI: o `.env` e do usuario."""
    monkeypatch.setenv('ADRI_DESENVOLVEDOR_DISPOSITIVO', IDENTIDADE)
    monkeypatch.setenv('ADRI_DESENVOLVEDOR_IPS', IP)
    monkeypatch.setenv('ADRI_LICENCA_ADMIN_TOKEN', TOKEN_ADMIN)

    assert vinculo['autorizar']() is False


def test_sem_ip_publico_o_acesso_e_negado(vinculo, monkeypatch):
    vinculo['segredos'].gravar({'ADRI_LICENCA_ADMIN_TOKEN': TOKEN_ADMIN})
    monkeypatch.setattr(vinculo['modulo'], '_ip_publico_atual', lambda: '')

    assert vinculo['autorizar']() is False


def test_sem_identidade_do_computador_o_acesso_e_negado(vinculo, ambiente, monkeypatch):
    vinculo['segredos'].gravar({'ADRI_LICENCA_ADMIN_TOKEN': TOKEN_ADMIN})
    monkeypatch.setattr(ambiente['licenca_remota'], 'identidade_instalacao', lambda: '')

    assert vinculo['autorizar']() is False


def test_computador_ja_vinculado_e_ip_conhecido_nao_consultam_a_central(vinculo, monkeypatch):
    vinculo['autorizar'](TOKEN_ADMIN)
    vinculo['consultas'].clear()
    _esquecer_cache(vinculo, monkeypatch)

    assert vinculo['autorizar']() is True
    assert vinculo['consultas'] == []


def test_ip_novo_revalida_a_chave_antes_de_entrar_na_lista(vinculo, monkeypatch):
    vinculo['segredos'].gravar({'ADRI_LICENCA_ADMIN_TOKEN': TOKEN_ADMIN})
    vinculo['autorizar']()
    vinculo['consultas'].clear()
    _esquecer_cache(vinculo, monkeypatch)
    monkeypatch.setattr(vinculo['modulo'], '_ip_publico_atual', lambda: '198.51.100.7')

    assert vinculo['autorizar']() is True
    assert vinculo['consultas'] == [TOKEN_ADMIN]
    assert _cofre(vinculo, 'ADRI_DESENVOLVEDOR_IPS') == IP + ',198.51.100.7'


def test_ip_novo_e_recusado_quando_a_central_nao_confirma_a_chave(vinculo, monkeypatch):
    vinculo['segredos'].gravar({'ADRI_LICENCA_ADMIN_TOKEN': TOKEN_ADMIN})
    vinculo['autorizar']()
    _esquecer_cache(vinculo, monkeypatch)
    monkeypatch.setattr(vinculo['modulo'], '_ip_publico_atual', lambda: '198.51.100.7')
    vinculo['central'].aceita = False

    assert vinculo['autorizar']() is False
    assert _cofre(vinculo, 'ADRI_DESENVOLVEDOR_IPS') == IP


def test_a_lista_de_ips_guarda_so_os_oito_mais_recentes(vinculo, monkeypatch):
    vinculo['segredos'].gravar({'ADRI_LICENCA_ADMIN_TOKEN': TOKEN_ADMIN})
    for final in range(1, 11):
        _esquecer_cache(vinculo, monkeypatch)
        monkeypatch.setattr(vinculo['modulo'], '_ip_publico_atual',
                            lambda final=final: f'198.51.100.{final}')
        assert vinculo['autorizar']() is True

    ips = _cofre(vinculo, 'ADRI_DESENVOLVEDOR_IPS').split(',')
    assert ips == [f'198.51.100.{final}' for final in range(3, 11)]


def test_cofre_levado_para_outro_computador_nao_leva_o_acesso(vinculo, ambiente, monkeypatch):
    """Marcador de outra maquina + IP fora da lista: nada feito."""
    vinculo['segredos'].gravar({'ADRI_LICENCA_ADMIN_TOKEN': TOKEN_ADMIN})
    vinculo['autorizar']()
    _esquecer_cache(vinculo, monkeypatch)
    monkeypatch.setattr(ambiente['licenca_remota'], 'identidade_instalacao', lambda: 'b' * 64)
    monkeypatch.setattr(vinculo['modulo'], '_ip_publico_atual', lambda: '198.51.100.7')

    assert vinculo['autorizar']() is False
    assert _cofre(vinculo, 'ADRI_DESENVOLVEDOR_DISPOSITIVO') == IDENTIDADE


def test_resultado_fica_em_cache_por_alguns_segundos(vinculo, monkeypatch):
    """A checagem roda a cada requisicao do desenvolvedor; sem cache, cada
    clique custaria uma consulta ao ipify."""
    vinculo['autorizar'](TOKEN_ADMIN)
    chamadas = []
    monkeypatch.setattr(vinculo['modulo'], '_ip_publico_atual',
                        lambda: chamadas.append(1) or IP)

    assert vinculo['autorizar']() is True
    assert vinculo['autorizar']() is True
    assert chamadas == []


def test_ip_invalido_gravado_no_cofre_e_descartado(vinculo, monkeypatch):
    vinculo['segredos'].gravar({
        'ADRI_LICENCA_ADMIN_TOKEN': TOKEN_ADMIN,
        'ADRI_DESENVOLVEDOR_DISPOSITIVO': IDENTIDADE,
        'ADRI_DESENVOLVEDOR_IPS': 'nao-e-ip,' + IP,
    })

    assert vinculo['autorizar']() is True
    assert _cofre(vinculo, 'ADRI_DESENVOLVEDOR_IPS') == IP


# =============================================================================
# Login e configuracao inicial do desenvolvedor
# =============================================================================
def test_desenvolvedor_nao_entra_fora_do_computador_autorizado(ambiente, http):
    ambiente['database'].criar_usuario('dev', SENHA, 'desenvolvedor')

    resposta = _entrar(http, 'dev')

    assert resposta.status_code == 403
    assert not _abriu_sessao(resposta)


def test_sessao_de_desenvolvedor_copiada_para_outro_computador_nao_vale(ambiente, http, monkeypatch):
    """A sessao mora no SQLite: copiar banco e cookie nao pode levar o painel."""
    autorizado = {'vale': True}
    monkeypatch.setattr(ambiente['auth_local'], '_autorizar_dispositivo_desenvolvedor',
                        lambda *_a, **_k: autorizado['vale'])
    ambiente['database'].criar_usuario('dev', SENHA, 'desenvolvedor')
    _entrar(http, 'dev')
    assert http.get('/api/auth/local/usuarios', headers=CABECALHOS).status_code == 200

    autorizado['vale'] = False

    assert http.get('/api/auth/local/usuarios', headers=CABECALHOS).status_code == 403
    assert _eu(http).status_code == 401


def test_configuracao_inicial_cria_o_desenvolvedor_uma_unica_vez(ambiente, http, vinculo):
    corpo = {'username': 'dono', 'senha': SENHA, 'email': 'd@exemplo.local',
             'chave_ativacao': TOKEN_ADMIN}

    primeira = _post(http, '/setup', corpo)
    segunda = _post(http, '/setup', {**corpo, 'username': 'outro-dono'})

    assert primeira.status_code == 201
    assert primeira.get_json()['usuario']['role'] == 'desenvolvedor'
    assert _eu(http).get_json()['usuario']['username'] == 'dono'
    assert segunda.status_code == 409
    assert ambiente['database'].obter_usuario_por_username('outro-dono') is None


def test_configuracao_inicial_recusa_chave_que_a_central_nao_reconhece(ambiente, http, vinculo):
    vinculo['central'].aceita = False

    resposta = _post(http, '/setup', {'username': 'dono', 'senha': SENHA, 'email': '',
                                      'chave_ativacao': TOKEN_ADMIN})

    assert resposta.status_code == 403
    assert ambiente['database'].existe_algum_usuario() is False


def test_configuracao_inicial_sem_a_chave_do_fornecedor_e_recusada(ambiente, http, vinculo):
    resposta = _post(http, '/setup', {'username': 'dono', 'senha': SENHA, 'email': ''})

    assert resposta.status_code == 403
    assert ambiente['database'].existe_algum_usuario() is False


@pytest.mark.parametrize('corpo', [
    None,
    {'username': '', 'senha': SENHA, 'email': '', 'chave_ativacao': TOKEN_ADMIN},
    {'username': 'x' * 81, 'senha': SENHA, 'email': '', 'chave_ativacao': TOKEN_ADMIN},
    {'username': 'dono', 'senha': 'curta', 'email': '', 'chave_ativacao': TOKEN_ADMIN},
    {'username': 'dono', 'senha': SENHA, 'email': 'e' * 255, 'chave_ativacao': TOKEN_ADMIN},
])
def test_configuracao_inicial_malformada_e_recusada(ambiente, http, vinculo, corpo):
    assert _post(http, '/setup', corpo).status_code == 400
    assert ambiente['database'].existe_algum_usuario() is False
