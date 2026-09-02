"""
Testes da migracao do motor de exibicao: pywebview/WebView2 -> Electron.

O que estes testes protegem nao e uma funcao, e uma decisao de arquitetura:
o processo Python virou backend puro (`backend/servidor.py`) e a janela passou
a ser do Electron. Sem eles, um `import webview` reintroduzido em qualquer
arquivo, ou um .spec ainda apontando para o antigo `main.py`, passa despercebido
ate a hora do build -- que so quebra na maquina de quem empacota.
"""
import ast
import json
import os
import re
import subprocess
import sys

import pytest

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
BACKEND = os.path.join(RAIZ, 'backend')

sys.path.insert(0, BACKEND)


def _arquivos_python():
    """Fontes Python do projeto, ignorando venv, build e node_modules."""
    # `backup/` guarda uma copia arquivada de um backend anterior. Varre-la
    # faria esta checagem valer para codigo congelado, que por definicao nao
    # muda mais -- e uma falha ali nao teria correcao possivel.
    ignorados = {'node_modules', '.venv', 'venv', '.uv-cache', 'build', 'dist',
                 'dist-electron', 'dist-instalador', '__pycache__', '.git',
                 'backup'}
    for pasta, subpastas, arquivos in os.walk(RAIZ):
        subpastas[:] = [s for s in subpastas if s not in ignorados]
        for arquivo in arquivos:
            if arquivo.endswith('.py'):
                yield os.path.join(pasta, arquivo)


def _ler(caminho):
    with open(caminho, encoding='utf-8') as f:
        return f.read()


# --------------------------------------------------------------------------
# Remocao do WebView
# --------------------------------------------------------------------------

def test_nenhum_fonte_python_importa_webview():
    """
    `import webview` em qualquer lugar significa que o WebView2 voltou a ser
    dependencia de execucao -- exatamente o que a migracao removeu.
    """
    culpados = []
    for caminho in _arquivos_python():
        arvore = ast.parse(_ler(caminho), filename=caminho)
        for no in ast.walk(arvore):
            if isinstance(no, ast.Import):
                nomes = [a.name for a in no.names]
            elif isinstance(no, ast.ImportFrom):
                nomes = [no.module or '']
            else:
                continue
            if any(n.split('.')[0] == 'webview' for n in nomes):
                culpados.append(os.path.relpath(caminho, RAIZ))
    assert culpados == [], f"webview ainda importado em: {culpados}"


def test_pywebview_fora_das_dependencias():
    requisitos = _ler(os.path.join(BACKEND, 'requirements.txt')).lower()
    assert 'pywebview' not in requisitos


def test_main_py_do_pywebview_nao_existe_mais():
    """O antigo entrypoint hospedava a janela; quem serve agora e servidor.py."""
    assert not os.path.exists(os.path.join(RAIZ, 'main.py'))
    assert os.path.exists(os.path.join(BACKEND, 'servidor.py'))


# --------------------------------------------------------------------------
# Backend headless
# --------------------------------------------------------------------------

def test_servidor_expoe_app_em_loopback():
    import servidor
    assert servidor.HOST == '127.0.0.1', "o backend nao pode escutar na rede"
    assert servidor.PORTA == 5000, "o redirect_uri do OAuth depende desta porta"
    assert callable(servidor.main)


def test_servidor_importa_sem_dependencia_de_gui():
    """
    Importar o backend num processo limpo prova que ele nao arrasta nada de
    janela. Um subprocesso e necessario: no processo de teste os modulos ja
    estao carregados e um import quebrado passaria batido.
    """
    codigo = (
        'import sys; sys.path.insert(0, r"%s");'
        'import servidor;'
        'assert "webview" not in sys.modules;'
        'print(servidor.PORTA)' % BACKEND
    )
    resultado = subprocess.run(
        [sys.executable, '-c', codigo],
        capture_output=True, text=True, cwd=BACKEND,
    )
    assert resultado.returncode == 0, resultado.stderr
    assert '5000' in resultado.stdout


def test_servidor_nao_liga_o_reloader():
    """
    O reloader duplicaria o processo Python e o Electron perderia a referencia
    do filho que precisa encerrar junto com a janela.
    """
    fonte = _ler(os.path.join(BACKEND, 'servidor.py'))
    assert 'use_reloader=False' in fonte
    assert 'debug=False' in fonte


# --------------------------------------------------------------------------
# Electron
# --------------------------------------------------------------------------

@pytest.fixture(scope='module')
def package_json():
    return json.loads(_ler(os.path.join(RAIZ, 'package.json')))


def test_package_json_aponta_para_o_bundle_compilado(package_json):
    assert package_json['main'] == 'dist-electron/main.js'
    assert 'electron' in package_json['devDependencies']
    assert 'typescript' in package_json['devDependencies']


def test_empacotamento_leva_o_backend_junto(package_json):
    """Sem o backend em extraResources o instalador gera uma janela vazia."""
    destinos = [r['to'] for r in package_json['build']['extraResources']]
    assert 'backend' in destinos


def test_janela_do_electron_e_isolada():
    """
    A pagina vem por HTTP e nao precisa do Node. Manter o isolamento impede
    que um XSS no frontend alcance o sistema de arquivos.
    """
    fonte = _ler(os.path.join(RAIZ, 'electron', 'main.ts'))
    assert 'contextIsolation: true' in fonte
    assert 'nodeIntegration: false' in fonte
    assert 'sandbox: true' in fonte
    assert 'webSecurity: true' in fonte


def test_electron_encerra_o_backend_ao_sair():
    """Sem isso o Python sobrevive a janela e a proxima abertura acha a porta ocupada."""
    fonte = _ler(os.path.join(RAIZ, 'electron', 'main.ts'))
    assert "'before-quit'" in fonte
    assert 'pararBackend' in fonte


def test_electron_usa_a_mesma_porta_do_backend():
    fonte = _ler(os.path.join(RAIZ, 'electron', 'backend.ts'))
    assert 'PORTA = 5000' in fonte
    assert "HOST = '127.0.0.1'" in fonte


def test_typescript_em_modo_estrito():
    config = _ler(os.path.join(RAIZ, 'tsconfig.json'))
    assert '"strict": true' in config


# --------------------------------------------------------------------------
# Empacotamento
# --------------------------------------------------------------------------

def test_spec_do_pyinstaller_empacota_o_backend():
    """
    O .spec passa a gerar o executavel do backend -- console, sem GUI --,
    consumido pelo electron-builder via extraResources.
    """
    spec = _ler(os.path.join(RAIZ, 'AdriPoltronasBackend.spec'))
    assert "servidor.py" in spec
    assert "'main.py'" not in spec
    assert re.search(r"name=['\"]AdriPoltronasBackend['\"]", spec)


def test_gitignore_cobre_artefatos_do_node():
    ignore = _ler(os.path.join(RAIZ, '.gitignore'))
    for padrao in ('node_modules/', 'dist-electron/', 'dist-instalador/'):
        assert padrao in ignore, f"{padrao} nao esta no .gitignore"


# --------------------------------------------------------------------------
# Comportamento do entrypoint
# --------------------------------------------------------------------------

# O comportamento de `preparar_banco()` -- quando cair para o schema basico e
# quando recusar a subir -- vive em tests/test_inicializacao_banco.py, que
# monta cada estado de banco num arquivo temporario. O teste que ficava aqui
# exercitava o banco real da maquina e so passava por acaso.


def test_main_desiste_quando_o_banco_nao_inicializa(monkeypatch):
    """Sem banco nao ha o que servir: melhor sair com codigo != 0 do que
    deixar o Electron abrir a janela em cima de um backend inutil."""
    import servidor

    def explode():
        raise RuntimeError('disco cheio')

    subiu = []
    monkeypatch.setattr(servidor, 'preparar_banco', explode)
    monkeypatch.setattr(servidor.app, 'run', lambda **_: subiu.append(True))

    assert servidor.main() == 1
    assert subiu == [], "o Flask nao pode subir sem banco"


def test_main_serve_em_loopback_sem_reloader(monkeypatch):
    import servidor

    argumentos = {}
    monkeypatch.setattr(servidor, 'preparar_banco', lambda: None)
    monkeypatch.setattr(servidor.app, 'run', lambda **kw: argumentos.update(kw))

    assert servidor.main() == 0
    assert argumentos['host'] == '127.0.0.1'
    assert argumentos['port'] == 5000
    assert argumentos['use_reloader'] is False
    assert argumentos['debug'] is False


def test_icone_tem_camada_de_256px():
    """
    O NSIS do electron-builder recusa o build com `image must be at least
    256x256`. O arquivo tinha uma unica camada de 150x150 e o instalador nao
    era gerado -- falha que so aparece no fim de um build de varios minutos.
    """
    import struct

    caminho = os.path.join(RAIZ, 'icone_sistema.ico')
    with open(caminho, 'rb') as arquivo:
        cabecalho = arquivo.read(6)
        _, _, quantidade = struct.unpack('<HHH', cabecalho)
        entradas = arquivo.read(16 * quantidade)

    # No formato ICO, largura/altura 0 significa 256.
    larguras = [entradas[i * 16] or 256 for i in range(quantidade)]
    assert max(larguras) >= 256, f"maior camada: {max(larguras)}px"
