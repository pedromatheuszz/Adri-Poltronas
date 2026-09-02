"""
Testes da segunda interface, em C++/Qt.

O projeto passou a ter duas janelas sobre o mesmo backend: a do Electron e a do
Qt. O que quebra nesse arranjo nao e o C++ em si -- disso cuidam os testes do
proprio qt-app, rodados pelo ctest -- e sim a *divergencia* entre os tres
lados. Se o Qt apontar para outra porta, ou o .spec renomear o executavel do
backend, cada interface passa a falar com um servidor diferente e nada acusa
ate alguem abrir o app.

Estes testes leem os fontes e conferem que Python, TypeScript e C++ continuam
combinando: mesma porta, mesmo host, mesmo entrypoint, mesmo nome do
executavel empacotado.
"""
import os
import re

import pytest

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
QT_APP = os.path.join(RAIZ, 'qt-app')


def _ler(*partes):
    with open(os.path.join(*partes), encoding='utf-8') as arquivo:
        return arquivo.read()


@pytest.fixture(scope='module')
def processo_backend_hpp():
    return _ler(QT_APP, 'src', 'ProcessoBackend.h')


@pytest.fixture(scope='module')
def processo_backend_cpp():
    return _ler(QT_APP, 'src', 'ProcessoBackend.cpp')


# --------------------------------------------------------------------------
# Estrutura
# --------------------------------------------------------------------------

def test_projeto_qt_existe_com_cmake():
    assert os.path.isfile(os.path.join(QT_APP, 'CMakeLists.txt'))
    assert os.path.isdir(os.path.join(QT_APP, 'src'))
    assert os.path.isdir(os.path.join(QT_APP, 'tests'))


def test_logica_fica_em_biblioteca_separada_do_main():
    """
    Sem a biblioteca estatica, os testes teriam de link o `main()` junto e a
    unica forma de exercitar a interface seria pela GUI, na mao.
    """
    cmake = _ler(QT_APP, 'CMakeLists.txt')
    assert 'add_library(adri_qt_core' in cmake
    assert 'src/main.cpp' not in cmake.split('add_executable(AdriPoltronasQt')[0]


def test_cada_fonte_do_qt_tem_teste_declarado():
    cmake = _ler(QT_APP, 'CMakeLists.txt')
    for nome in ('cliente_api', 'modelo_clientes', 'processo_backend'):
        assert f'add_test(NAME {nome}' in cmake, f'{nome} nao esta no ctest'
        assert os.path.isfile(os.path.join(QT_APP, 'tests', f'test_{nome}.cpp'))


# --------------------------------------------------------------------------
# Contrato entre as duas janelas e o backend
# --------------------------------------------------------------------------

def test_qt_usa_a_mesma_porta_do_electron_e_do_flask(processo_backend_hpp):
    """5000 e fixa: o redirect_uri do OAuth da Microsoft aponta para ela."""
    import servidor

    assert 'kPorta = 5000' in processo_backend_hpp
    assert 'kHost[] = "127.0.0.1"' in processo_backend_hpp
    assert 'PORTA = 5000' in _ler(RAIZ, 'electron', 'backend.ts')
    assert servidor.PORTA == 5000
    assert servidor.HOST == '127.0.0.1'


def test_qt_sobe_o_mesmo_entrypoint_python(processo_backend_cpp):
    assert 'backend/servidor.py' in processo_backend_cpp


def test_qt_e_electron_procuram_o_mesmo_executavel_empacotado(processo_backend_cpp):
    """O nome vem do .spec; renomear la sem renomear aqui gera janela vazia."""
    spec = _ler(RAIZ, 'AdriPoltronasBackend.spec')
    nome = re.search(r"name=['\"](AdriPoltronas\w+)['\"]", spec).group(1)

    assert f'{nome}.exe' in processo_backend_cpp
    assert f'{nome}.exe' in _ler(RAIZ, 'electron', 'backend.ts')


def test_qt_sonda_a_identidade_antes_de_subir_o_proprio(processo_backend_cpp):
    """
    As duas janelas podem estar abertas ao mesmo tempo. Sem esta checagem, a
    segunda tentaria subir outro Flask na mesma porta e morreria.

    Ate a 1.2.1 bastava um `connect` TCP: qualquer servidor de qualquer
    projeto era adotado como se fosse o backend do ERP. A sonda agora
    pergunta a /api/health QUEM esta atendendo, e se aceita a credencial que
    temos em maos.
    """
    corpo = processo_backend_cpp.split('bool ProcessoBackend::iniciar')[1]
    assert corpo.index('sondarPorta(capacidade)') < corpo.index('new QProcess')

    for desfecho in ('Nosso', 'Livre', 'Estranho', 'RecusouCapacidade'):
        assert f'EstadoDaPorta::{desfecho}' in corpo,             f'o desfecho {desfecho} nao e tratado ao iniciar'


def test_qt_envia_o_token_de_capacidade_na_api(processo_backend_cpp):
    """
    O Qt era o buraco na protecao: sondava a porta e nao mandava cabecalho
    nenhum. Ou subia um backend SEM exigencia de token -- desfazendo a
    protecao para todo mundo --, ou tomava 403 ao falar com o do Electron.
    """
    cliente_api = _ler(RAIZ, 'qt-app', 'src', 'ClienteApi.cpp')
    assert 'kHeaderDaCapacidade' in cliente_api,         'o ClienteApi nao injeta o cabecalho de capacidade'
    # Nenhum ponto pode montar a requisicao por fora do helper: e assim que
    # uma chamada volta a sair sem o token.
    assert 'QNetworkRequest(url' not in cliente_api
    assert 'rede_->get(QNetworkRequest(' not in cliente_api


def test_qt_repassa_a_capacidade_ao_backend_que_sobe(processo_backend_cpp):
    """Sem isso, o backend iniciado pela janela Qt nao exigiria token de
    ninguem -- e a protecao valeria so quando o Electron subisse primeiro."""
    assert 'kVariavelDaCapacidade' in processo_backend_cpp


def test_qt_le_a_capacidade_do_mesmo_lugar_que_as_outras_pilhas():
    """
    As tres implementacoes leem o MESMO arquivo. `QStandardPaths` nao serve:
    `GenericConfigLocation` no Windows resolve para %LOCALAPPDATA%, e nao
    para o Roaming onde o Python e o .NET escrevem -- foi assim que a
    primeira versao criou um segundo arquivo, com outro token.
    """
    capacidade = _ler(RAIZ, 'qt-app', 'src', 'Capacidade.cpp')
    assert 'qEnvironmentVariable("APPDATA")' in capacidade
    # A forma do CODIGO, e nao a palavra solta: o comentario do proprio
    # arquivo cita `GenericConfigLocation` justamente para explicar por que
    # ela nao serve, e uma busca ingenua acusaria o comentario.
    assert 'QStandardPaths::GenericConfigLocation' not in capacidade
    assert '.capacidade' in capacidade


def test_qt_encerra_o_backend_que_iniciou(processo_backend_cpp):
    corpo = processo_backend_cpp.split('void ProcessoBackend::encerrar')[1]
    assert 'terminate()' in corpo
    assert 'kill()' in corpo


def test_qt_nao_mata_backend_de_outra_instancia(processo_backend_cpp):
    """
    Ao reaproveitar um servidor que nao e nosso, encerrar a janela Qt nao pode
    derrubar o backend da janela do Electron que estava usando ele.
    """
    corpo = processo_backend_cpp.split('void ProcessoBackend::encerrar')[1]
    assert 'processoProprio_' in corpo


# --------------------------------------------------------------------------
# Regras do projeto que valem para as duas interfaces
# --------------------------------------------------------------------------

def _codigo_sem_comentarios(fonte):
    """
    Descarta // e /* */ antes de procurar padroes no codigo.

    Sem isso o proprio comentario que explica a regra ("a janela Qt nao fala
    com o SQLite") derrubava o teste que verifica a regra.
    """
    sem_bloco = re.sub(r'/\*.*?\*/', '', fonte, flags=re.S)
    return '\n'.join(re.sub(r'//.*', '', linha) for linha in sem_bloco.splitlines())


def _fontes_do_qt():
    for arquivo in sorted(os.listdir(os.path.join(QT_APP, 'src'))):
        yield arquivo, _codigo_sem_comentarios(_ler(QT_APP, 'src', arquivo))


def test_qt_nao_fala_com_o_banco_direto():
    """
    Validacao, migrations e regras de negocio ficam no Python. A janela Qt
    consome a API -- duas UIs, um backend, uma fonte de verdade.
    """
    for arquivo, codigo in _fontes_do_qt():
        assert 'QSqlDatabase' not in codigo, f'{arquivo} acessa banco direto'
        assert 'QtSql' not in codigo, f'{arquivo} acessa banco direto'


def test_qt_so_conversa_com_loopback():
    """Nenhuma URL externa embutida: tudo passa pelo backend local."""
    # A URL do app e montada com placeholders do QString::arg ("http://%1:%2/"),
    # cujos valores sao as constantes kHost/kPorta -- cobertas em outro teste.
    permitidos = ('http://127.0.0.1', 'http://%1:%2')
    for arquivo, codigo in _fontes_do_qt():
        for url in re.findall(r'https?://[^\s"\')]+', codigo):
            assert url.startswith(permitidos), f'{arquivo}: {url}'


def test_build_do_qt_fica_fora_do_versionamento():
    ignore = _ler(RAIZ, '.gitignore')
    assert 'qt-app/build/' in ignore
