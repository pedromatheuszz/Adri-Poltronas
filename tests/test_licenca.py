"""
Licenca de uso: 30 dias de teste, depois compra.

O QUE ESTES TESTES GARANTEM, E O QUE NAO GARANTEM
Nao garantem que a licenca seja inviolavel -- ela nao e, e `licenca.py` diz
isso na primeira linha. O aplicativo roda inteiro na maquina do cliente, entao
quem tem administrador ali contorna qualquer bloqueio escrito aqui.

O que garantem e que os dois contornos ACIDENTAIS nao acontecam: apagar o
arquivo do perfil e restaurar um backup antigo do banco sao coisas que um
operador faz sem ma intencao, e nenhuma das duas pode devolver o prazo. E
garantem o contrario com a mesma forca: ninguem perde o acesso por engano.
"""
import datetime as dt
import os
import sys

import pytest

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(RAIZ, 'backend'))

import capacidade  # noqa: E402
import database  # noqa: E402
import licenca  # noqa: E402


@pytest.fixture
def instalacao(monkeypatch, tmp_path):
    """Uma instalacao limpa: banco proprio, arquivo de perfil proprio."""
    banco = str(tmp_path / 'licenca.db')
    monkeypatch.setenv('ADRI_DB_PATH', banco)
    monkeypatch.setattr(database, 'DB_PATH', banco)
    database.criar_tabela()
    return tmp_path


@pytest.fixture
def relogio(monkeypatch):
    """Controle do tempo. `licenca._agora` e o unico ponto que le o relogio."""
    partida = licenca._agora()

    class _Relogio:
        def __init__(self):
            self.deslocamento = dt.timedelta(0)

        def avancar(self, dias):
            self.deslocamento += dt.timedelta(days=dias)

        def voltar(self, dias):
            self.deslocamento -= dt.timedelta(days=dias)

    controle = _Relogio()
    monkeypatch.setattr(licenca, '_agora',
                        lambda: partida + controle.deslocamento)
    return controle


# =============================================================================
# O periodo de teste
# =============================================================================
def test_primeira_abertura_da_trinta_dias(instalacao):
    situacao = licenca.situacao()
    assert situacao['estado'] == licenca.ESTADO_TESTE
    assert situacao['dias_restantes'] == licenca.DIAS_DE_TESTE
    assert licenca.esta_liberado() is True


def test_o_preco_e_o_de_venda(instalacao):
    """R$ 2.000,00 em centavos, na mesma convencao do resto do financeiro."""
    assert licenca.VALOR_DA_LICENCA_CENTAVOS == 200000
    assert licenca.situacao()['valor_centavos'] == 200000


def test_a_contagem_anda_com_o_calendario(instalacao, relogio):
    licenca.situacao()
    relogio.avancar(10)
    assert licenca.situacao()['dias_restantes'] == 20


def test_no_trigesimo_primeiro_dia_expira(instalacao, relogio):
    licenca.situacao()
    relogio.avancar(licenca.DIAS_DE_TESTE + 1)
    situacao = licenca.situacao()
    assert situacao['estado'] == licenca.ESTADO_EXPIRADA
    assert situacao['dias_restantes'] == 0
    assert licenca.esta_liberado() is False


def test_o_ultimo_dia_ainda_esta_liberado(instalacao, relogio):
    """Fronteira. Errar para o lado de bloquear cedo tira do cliente um dia
    pelo qual ele nao foi avisado."""
    licenca.situacao()
    relogio.avancar(licenca.DIAS_DE_TESTE - 1)
    assert licenca.esta_liberado() is True


# =============================================================================
# O relogio do sistema
# =============================================================================
def test_atrasar_o_relogio_nao_devolve_prazo(instalacao, relogio):
    """
    Sem a marca d'agua, atrasar o relogio do Windows estenderia o teste para
    sempre -- e e a primeira coisa que qualquer um tenta.

    A marca guarda a data mais adiantada ja vista e nao retrocede: o relogio
    atrasado CONGELA a contagem em vez de reverte-la.
    """
    licenca.situacao()
    relogio.avancar(20)
    assert licenca.situacao()['dias_restantes'] == 10

    relogio.voltar(15)
    assert licenca.situacao()['dias_restantes'] == 10


def test_relogio_atrasado_nao_ressuscita_licenca_expirada(instalacao, relogio):
    licenca.situacao()
    relogio.avancar(40)
    assert licenca.esta_liberado() is False

    relogio.voltar(35)
    assert licenca.esta_liberado() is False


# =============================================================================
# Os dois contornos acidentais
# =============================================================================
def test_apagar_o_arquivo_do_perfil_nao_reinicia_o_teste(instalacao, relogio):
    """O lado do banco sobrevive, e a reconciliacao pega a instalacao mais
    antiga dos dois."""
    licenca.situacao()
    relogio.avancar(25)

    os.remove(licenca.caminho_do_arquivo())
    assert licenca.situacao()['dias_restantes'] == 5


def test_restaurar_um_banco_antigo_nao_reinicia_o_teste(instalacao, relogio):
    """
    Restaurar backup e funcao legitima e documentada deste app, entao um banco
    velho voltando ao lugar nao pode ser lido como instalacao nova. O lado do
    arquivo sobrevive.
    """
    licenca.situacao()
    relogio.avancar(25)

    with database.conectar() as conexao:
        conexao.execute("DELETE FROM licenca")

    assert licenca.situacao()['dias_restantes'] == 5


def test_apagar_os_dois_lados_reinicia_o_teste(instalacao, relogio):
    """
    O limite honesto, escrito como teste para que ninguem se iluda com o que
    o controle alcanca: quem apaga OS DOIS lados comeca de novo. E deliberado,
    e nao acontece por acidente.
    """
    licenca.situacao()
    relogio.avancar(25)

    os.remove(licenca.caminho_do_arquivo())
    with database.conectar() as conexao:
        conexao.execute("DELETE FROM licenca")

    assert licenca.situacao()['dias_restantes'] == licenca.DIAS_DE_TESTE


def test_arquivo_adulterado_e_ignorado_e_nao_aceito(instalacao, relogio):
    """
    Um arquivo que nao decifra nao pode virar "estado em branco confiavel" --
    seria a porta de entrada para "reescreva o arquivo e ganhe 30 dias". Ele e
    descartado, e o lado do banco decide.
    """
    licenca.situacao()
    relogio.avancar(25)

    with open(licenca.caminho_do_arquivo(), 'w', encoding='utf-8') as arquivo:
        arquivo.write('{"instalado_em": "2099-01-01T00:00:00"}')

    assert licenca.situacao()['dias_restantes'] == 5


# =============================================================================
# O pagamento
# =============================================================================
def test_licenca_paga_nao_expira_mais(instalacao, relogio):
    licenca.registrar_pagamento('mp-123')
    relogio.avancar(400)

    situacao = licenca.situacao()
    assert situacao['estado'] == licenca.ESTADO_PAGA
    assert situacao['dias_restantes'] is None
    assert situacao['pagamento_id'] == 'mp-123'
    assert licenca.esta_liberado() is True


def test_o_pagamento_sobrevive_a_perda_de_um_dos_lados(instalacao):
    """Quem pagou nao pode voltar a ser bloqueado por um arquivo apagado."""
    licenca.registrar_pagamento('mp-456')

    os.remove(licenca.caminho_do_arquivo())
    assert licenca.situacao()['estado'] == licenca.ESTADO_PAGA

    licenca.situacao()  # regrava o arquivo a partir do banco
    with database.conectar() as conexao:
        conexao.execute("DELETE FROM licenca")
    assert licenca.situacao()['estado'] == licenca.ESTADO_PAGA


def test_a_referencia_da_instalacao_e_estavel(instalacao):
    """E o `external_reference` da cobranca: se mudasse a cada chamada, o
    pagamento deixaria de estar ligado a esta maquina."""
    primeira = licenca.situacao()['referencia']
    assert primeira.startswith('adri-licenca-')
    assert licenca.situacao()['referencia'] == primeira


def test_cobranca_pendente_e_lembrada_entre_aberturas(instalacao):
    """O app pode ser fechado com o Pix na tela. A verificacao automatica da
    proxima abertura precisa saber a quem perguntar."""
    licenca.guardar_pagamento_pendente('mp-789')
    assert licenca.situacao()['pagamento_id'] == 'mp-789'
    assert licenca.situacao()['estado'] == licenca.ESTADO_TESTE


def test_isencoes_sao_apenas_as_rotas_da_propria_licenca():
    """Uma isencao a mais e uma porta aberta no bloqueio. As rotas existentes
    sao as que permitem sair dele."""
    assert licenca.ROTAS_ISENTAS == frozenset({
        '/api/licenca/status',
        '/api/licenca/cobranca',
        '/api/licenca/verificar',
        '/api/licenca/teste',
    })


# =============================================================================
# O bloqueio, sobre o app de verdade
#
# Com TESTING ligado o guarda e propositalmente transparente -- senao a suite
# inteira precisaria de licenca. Estes testes o desligam e apresentam o token
# de capacidade e a sessao, para que a UNICA recusa possivel seja a licenca.
# =============================================================================
TOKEN_DE_CAPACIDADE = 'token-do-app-na-licenca'
CABECALHOS = {capacidade.NOME_DO_HEADER: TOKEN_DE_CAPACIDADE,
              'Origin': 'http://localhost'}


@pytest.fixture
def cliente_com_guardas(monkeypatch, tmp_path):
    banco = str(tmp_path / 'guarda-licenca.db')
    monkeypatch.setenv('ADRI_DB_PATH', banco)
    monkeypatch.setenv(capacidade.VARIAVEL_DE_AMBIENTE, TOKEN_DE_CAPACIDADE)
    monkeypatch.delenv(capacidade.VARIAVEL_DE_DESLIGAMENTO, raising=False)

    import app as modulo_app

    monkeypatch.setattr(database, 'DB_PATH', banco)
    database.criar_tabela()
    user_id = database.criar_usuario('operador', 'senha-de-teste', 'usuario', 'operador@exemplo.local')
    token = 'token-local-licenca'
    database.salvar_sessao_local(token, user_id, 'operador', 'usuario')

    modulo_app.app.config['TESTING'] = False
    try:
        with modulo_app.app.test_client() as cliente:
            cliente.set_cookie(database.NOME_COOKIE_SESSAO_LOCAL, token)
            yield cliente
    finally:
        modulo_app.app.config['TESTING'] = True


def test_durante_o_teste_a_api_responde(cliente_com_guardas):
    assert cliente_com_guardas.get('/api/clientes', headers=CABECALHOS).status_code == 200


def test_expirada_a_api_recusa_com_402(cliente_com_guardas, relogio):
    """
    402 Payment Required, e nao 403: o codigo carrega informacao util. E o que
    permite a interface distinguir "pague" de "conecte-se" sem inspecionar
    texto de mensagem.
    """
    licenca.situacao()
    relogio.avancar(licenca.DIAS_DE_TESTE + 1)

    resposta = cliente_com_guardas.get('/api/clientes', headers=CABECALHOS)

    assert resposta.status_code == 402
    corpo = resposta.get_json()
    assert corpo['licenca']['estado'] == licenca.ESTADO_EXPIRADA
    assert corpo['licenca']['valor_centavos'] == licenca.VALOR_DA_LICENCA_CENTAVOS


def test_expirada_a_escrita_tambem_para(cliente_com_guardas, relogio):
    licenca.situacao()
    relogio.avancar(licenca.DIAS_DE_TESTE + 1)

    resposta = cliente_com_guardas.post('/api/clientes', json={}, headers=CABECALHOS)
    assert resposta.status_code == 402


@pytest.mark.parametrize('rota', sorted(licenca.ROTAS_ISENTAS))
def test_expirada_as_rotas_da_licenca_continuam_respondendo(
        cliente_com_guardas, relogio, rota):
    """Sem isto o operador ficaria trancado do lado de fora com a chave
    dentro: nao poderia nem consultar a situacao, nem gerar a cobranca."""
    licenca.situacao()
    relogio.avancar(licenca.DIAS_DE_TESTE + 1)

    metodo = cliente_com_guardas.get if rota.endswith('status') else cliente_com_guardas.post
    resposta = metodo(rota, headers=CABECALHOS)
    assert resposta.status_code != 402


def test_expirada_a_sonda_de_identidade_continua_respondendo(cliente_com_guardas, relogio):
    """O Electron pergunta a /api/health quem esta na porta antes de adotar o
    backend. Bloquear ali faria o app nao abrir em vez de pedir pagamento."""
    licenca.situacao()
    relogio.avancar(licenca.DIAS_DE_TESTE + 1)

    assert cliente_com_guardas.get('/api/health', headers=CABECALHOS).status_code == 200


def test_paga_a_api_volta_a_responder(cliente_com_guardas, relogio):
    licenca.situacao()
    relogio.avancar(licenca.DIAS_DE_TESTE + 1)
    assert cliente_com_guardas.get('/api/clientes', headers=CABECALHOS).status_code == 402

    licenca.registrar_pagamento('mp-do-teste')

    assert cliente_com_guardas.get('/api/clientes', headers=CABECALHOS).status_code == 200


def test_a_licenca_nao_atropela_o_guarda_de_sessao(cliente_com_guardas, relogio):
    """
    Ordem dos guardas: sessao vem antes de licenca. Quem nao esta autenticado
    no app nao precisa saber em que pe esta a licenca dele -- e um 402 ali
    revelaria a situacao comercial para quem nao passou nem da porta.
    """
    licenca.situacao()
    relogio.avancar(licenca.DIAS_DE_TESTE + 1)
    with database.conectar() as conexao:
        conexao.execute("DELETE FROM sessao")

    resposta = cliente_com_guardas.get('/api/clientes', headers=CABECALHOS)
    assert resposta.status_code == 401
