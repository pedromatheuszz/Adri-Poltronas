"""
Testes ponta a ponta: o JavaScript da interface rodando num navegador de verdade.

POR QUE ESTE ARQUIVO EXISTE
O resto da suite exercita o backend com o cliente de teste do Flask e verifica
o front-end **lendo os arquivos e procurando trechos de texto**. Isso pega
regressao de contrato ("o seletor sumiu do HTML"), e nao pega nada do que
acontece quando o codigo roda: um `ReferenceError` numa funcao que so e
chamada por clique, um ouvinte registrado antes do elemento existir, um modal
que abre e nao fecha.

Foi exatamente assim que um defeito passou pela suite inteira durante a
migracao dos handlers `onclick` para comandos declarativos: os 36 atributos
estavam certos no HTML, o teste de markup passava, e o despachante morria com
`ReferenceError` porque uma das funcoes vive em outro arquivo, carregado
depois. Nenhum teste de string acharia isso.

COMO RODAR

    pip install pytest-playwright
    playwright install chromium
    cd backend && python -m pytest ../tests/test_e2e_interface.py -v

Sem o Playwright instalado, o arquivo inteiro e pulado -- a suite normal nao
depende dele. No CI ha um job proprio.
"""
import contextlib
import json
import os
import socket
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

playwright_api = pytest.importorskip(
    "playwright.sync_api",
    reason="Playwright nao instalado. Ver o cabecalho deste arquivo.",
)
sync_playwright = playwright_api.sync_playwright

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
BACKEND = os.path.join(RAIZ, 'backend')

TIMEOUT_BOOT_S = 40
TOKEN_E2E_SESSAO_LOCAL = 'token-de-sessao-local-ponta-a-ponta'


class _HandlerLicencaE2E(BaseHTTPRequestHandler):
    """API central mínima para exercitar o fluxo sem depender do Render."""

    def do_POST(self):
        if self.path != '/v1/licenses/sync':
            self.send_error(404)
            return
        tamanho = int(self.headers.get('Content-Length', '0'))
        dados = json.loads(self.rfile.read(tamanho) or b'{}')
        agora = datetime.now(timezone.utc)
        estado = self.server.estado_licenca
        expiracao = agora - timedelta(days=1) if estado == 'expired' else agora + timedelta(days=30)
        resposta = json.dumps({
            'license_id': dados.get('license_id', ''),
            'username': dados.get('username', ''),
            'email': dados.get('email', ''),
            'estado': estado,
            'inicio_em': agora.strftime('%Y-%m-%dT%H:%M:%SZ'),
            'expira_em': expiracao.strftime('%Y-%m-%dT%H:%M:%SZ'),
            'pago_em': '',
            'atualizado_em': agora.strftime('%Y-%m-%dT%H:%M:%SZ'),
        }).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(resposta)))
        self.end_headers()
        self.wfile.write(resposta)

    def log_message(self, _formato, *_argumentos):
        return


def _iniciar_licenca_e2e(estado):
    servidor = ThreadingHTTPServer(('127.0.0.1', 0), _HandlerLicencaE2E)
    servidor.estado_licenca = estado
    servidor.daemon_threads = True
    thread = threading.Thread(target=servidor.serve_forever, daemon=True)
    thread.start()
    url = f'http://127.0.0.1:{servidor.server_address[1]}'
    return servidor, thread, url


def _porta_livre() -> int:
    """
    Porta sorteada, e nao a 5000.

    A 5000 pode estar ocupada pelo aplicativo do desenvolvedor -- e o teste
    passaria conversando com o banco de producao dele.
    """
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def _semear_sessao(caminho_do_banco) -> None:
    """
    Grava uma sessão local e uma conexão Microsoft no banco de teste.

    O login local é obrigatório para usar o ERP; a sessão Microsoft fica
    presente para os testes da integração opcional com OneDrive/Excel.
    """
    sys.path.insert(0, BACKEND)
    import database

    original = database.DB_PATH
    database.DB_PATH = str(caminho_do_banco)
    try:
        database.criar_tabela()
        user_id = database.criar_usuario(
            'operador', 'senha-local-e2e-forte', 'usuario', 'operador@exemplo.local')
        database.salvar_sessao_local(
            TOKEN_E2E_SESSAO_LOCAL, user_id, 'operador', 'usuario')
        database.salvar_sessao("token-de-teste", "operador@exemplo.local")
    finally:
        database.DB_PATH = original


def _semear_cliente(caminho_do_banco) -> None:
    """
    Grava um cliente, e NAO uma sessao.

    Serve ao teste do estado desconectado: e preciso haver cadastro no banco
    para provar que ele nao aparece na tela. Um banco vazio deixaria passar
    exatamente o defeito que se quer pegar.
    """
    sys.path.insert(0, BACKEND)
    import database

    original = database.DB_PATH
    database.DB_PATH = str(caminho_do_banco)
    try:
        database.criar_tabela()
        database.salvar_cliente("Maria Souza", "89201-000", "Rua X",
                                "Centro", "Joinville", "Entrega", "")
    finally:
        database.DB_PATH = original


@contextlib.contextmanager
def _backend_no_ar(banco, estado_licenca='trial'):
    """Sobe o backend real sobre `banco` e devolve a URL base."""
    porta = _porta_livre()
    central, thread_central, url_central = _iniciar_licenca_e2e(estado_licenca)

    ambiente = {
        **os.environ,
        'ADRI_DB_PATH': str(banco),
        'APPDATA': str(banco.parent / 'appdata'),
        'ADRI_PORTA': str(porta),
        'PYTHONUNBUFFERED': '1',
        'ADRI_LICENCA_API_URL': url_central,
        # Nenhum segredo da máquina de quem roda o E2E deve habilitar o
        # bootstrap do desenvolvedor no banco temporário.
        'ADRI_LICENCA_ADMIN_TOKEN': '',
    }
    # Sem ADRI_API_TOKEN: a capacidade e injetada pelo Electron, e aqui o
    # navegador e o Playwright. Testar a capacidade e trabalho de
    # test_capacidade.py, que a exercita direto.
    #
    # Ate a 1.3.0 bastava remover a variavel: a exigencia caia sozinha. Isso
    # era o fail-open que a 1.3.1 fechou -- hoje a ausencia da variavel faz o
    # backend cair no token do perfil e continuar exigindo. Desligar virou
    # explicito, e este e exatamente o caso de uso do opt-in: um cliente que
    # nao tem como carregar o cabecalho.
    ambiente.pop('ADRI_API_TOKEN', None)
    ambiente['ADRI_API_SEM_TOKEN'] = '1'

    # A saida vai para ARQUIVO, e nao para um `subprocess.PIPE`.
    #
    # Com PIPE e ninguem lendo, o buffer do sistema (64 KB no Windows) enche e
    # o processo filho BLOQUEIA na proxima escrita. O Werkzeug registra uma
    # linha por requisicao, entao isso acontece depois de algumas dezenas de
    # cliques: o primeiro teste passava e todos os seguintes davam timeout de
    # navegacao, num servidor que parecia vivo e nao respondia mais.
    log = banco.parent / "backend.log"
    with open(log, "w", encoding="utf-8") as saida:
        processo = subprocess.Popen(
            [sys.executable, os.path.join(BACKEND, 'servidor.py')],  # noqa: S603 - argumentos fixos, montados no codigo e nao pela entrada
            cwd=BACKEND, env=ambiente,
            stdout=saida, stderr=subprocess.STDOUT, text=True,
        )

        base = f"http://127.0.0.1:{porta}"
        limite = time.time() + TIMEOUT_BOOT_S
        while time.time() < limite:
            if processo.poll() is not None:
                central.shutdown()
                central.server_close()
                thread_central.join(timeout=3)
                pytest.fail(
                    "o backend morreu ao subir:\n"
                    + log.read_text(encoding="utf-8", errors="replace")
                )
            try:
                with socket.create_connection(('127.0.0.1', porta), timeout=0.5):
                    break
            except OSError:
                time.sleep(0.25)
        else:
            processo.kill()
            central.shutdown()
            central.server_close()
            thread_central.join(timeout=3)
            pytest.fail(f"o backend nao respondeu em {TIMEOUT_BOOT_S}s")

        try:
            yield base
        finally:
            processo.terminate()
            try:
                processo.wait(timeout=5)
            except subprocess.TimeoutExpired:
                processo.kill()
            central.shutdown()
            central.server_close()
            thread_central.join(timeout=3)


@pytest.fixture(scope="module")
def servidor(tmp_path_factory):
    """Backend com sessao Microsoft gravada: o app em uso normal."""
    banco = tmp_path_factory.mktemp("e2e") / "e2e.db"
    _semear_sessao(banco)
    with _backend_no_ar(banco) as base:
        yield base


@pytest.fixture(scope="module")
def servidor_licenca_vencida(tmp_path_factory):
    """
    Backend com sessao, cadastro e o periodo de teste ja encerrado.

    O defeito que este cenario pega: `checarLoginExistente` chamava o
    carregamento dos dados direto, e ele roda ANTES de a licenca ser
    consultada. Com o teste vencido, as quatro requisicoes voltavam 402 e a
    tela ficava com os zeros escritos no HTML -- e, pior, marcava os dados como
    "ja carregados", de modo que pagar a licenca liberava a tela sem trazer
    dado nenhum.
    """
    banco = tmp_path_factory.mktemp("e2e-licenca") / "e2e.db"
    _semear_sessao(banco)
    _semear_cliente(banco)
    with _backend_no_ar(banco, estado_licenca='expired') as base:
        yield base


def _vencer_licenca(caminho_do_banco) -> None:
    """Empurra a instalacao para 45 dias atras, nos dois lados do estado."""
    import datetime

    sys.path.insert(0, BACKEND)
    os.environ["ADRI_DB_PATH"] = str(caminho_do_banco)
    import database
    import licenca

    original = database.DB_PATH
    database.DB_PATH = str(caminho_do_banco)
    try:
        dados = licenca._carregar_e_atualizar_marca()
        dados["instalado_em"] = licenca._texto(
            licenca._agora() - datetime.timedelta(days=45)
        )
        licenca._persistir(dados)
    finally:
        database.DB_PATH = original


@pytest.fixture(scope="module")
def servidor_sem_sessao(tmp_path_factory):
    """
    Backend COM cadastro e SEM sessao: o app aberto por quem nunca conectou.

    Ate a 1.3.0 esse estado nao existia -- a leitura respondia sem sessao e a
    tela carregava como qualquer outra. Fechada a folga, o mesmo app passou a
    exibir a casca com os zeros escritos no proprio HTML enquanto as chamadas
    voltavam 401 em silencio. Nao era um erro na tela: era numero errado com
    ar de numero certo.
    """
    banco = tmp_path_factory.mktemp("e2e-sem-sessao") / "e2e.db"
    _semear_cliente(banco)
    with _backend_no_ar(banco) as base:
        yield base


@pytest.fixture(scope="module")
def navegador():
    """
    Um navegador para o modulo inteiro.

    Subir um Chromium por teste custa alguns segundos vezes vinte testes. A
    isolacao que importa vem do contexto novo a cada teste -- cada um comeca
    sem cookie, sem localStorage e sem service worker do anterior.
    """
    with sync_playwright() as p:
        instancia = p.chromium.launch()
        yield instancia
        instancia.close()


def _preparar_contexto(navegador):
    """Contexto novo, com a rede de terceiros cortada."""
    contexto = navegador.new_context()

    # Ate a 1.5.0 era preciso neutralizar os CDNs aqui: o Leaflet e o Chart.js
    # vinham de fora, e num runner sem saida para a internet o teste travava
    # esperando por algo que nao era o objeto dele. Os stubs sairam junto com a
    # dependencia -- as duas bibliotecas agora sao servidas pelo proprio
    # backend, entao o navegador carrega as de verdade e o e2e exercita o que
    # o usuario realmente recebe.
    #
    # Os ladrilhos do mapa continuam cortados: vem da rede por natureza, e
    # desenhar o mapa nao e o que nenhum destes testes verifica.
    contexto.route("**tile.openstreetmap.org/**", lambda rota: rota.abort())
    return contexto


@pytest.fixture
def pagina_sem_sessao(navegador, servidor_sem_sessao):
    """A tela de login de quem abre o app sem uma sessão local."""
    contexto = _preparar_contexto(navegador)
    pagina = contexto.new_page()

    erros = []
    pagina.on("pageerror", lambda erro: erros.append(str(erro)))

    pagina.goto(servidor_sem_sessao, wait_until="load")
    # `state="attached"`, e nao visivel: as abas continuam no DOM e e o CSS
    # que as esconde enquanto o painel esta na tela. Esperar por visibilidade
    # aqui daria timeout justamente quando o comportamento esta CERTO.
    pagina.wait_for_selector("#aba-dashboard", state="attached", timeout=15000)
    pagina.wait_for_selector("#telaLogin:not([hidden])", timeout=15000)
    pagina.erros_de_javascript = erros

    yield pagina

    contexto.close()


@pytest.fixture
def pagina_licenca_vencida(navegador, servidor_licenca_vencida):
    contexto = _preparar_contexto(navegador)
    pagina = contexto.new_page()

    erros = []
    pagina.on("pageerror", lambda erro: erros.append(str(erro)))

    contexto.add_cookies([{
        'name': 'adri_sessao_local', 'value': TOKEN_E2E_SESSAO_LOCAL,
        'url': servidor_licenca_vencida, 'sameSite': 'Strict',
    }])
    pagina.goto(servidor_licenca_vencida, wait_until="load")
    pagina.wait_for_selector("#aba-dashboard", state="attached", timeout=15000)
    pagina.wait_for_selector("#telaPagamento:not([hidden])", timeout=15000)
    pagina.erros_de_javascript = erros

    yield pagina

    contexto.close()


@pytest.fixture
def pagina(navegador, servidor):
    contexto = navegador.new_context()
    pagina = contexto.new_page()

    erros = []
    pagina.on("pageerror", lambda erro: erros.append(str(erro)))

    # Ate a 1.5.0 era preciso neutralizar os CDNs aqui: o Leaflet e o Chart.js
    # vinham de fora, e num runner sem saida para a internet o teste travava
    # esperando por algo que nao era o objeto dele. Os stubs sairam junto com a
    # dependencia -- as duas bibliotecas agora sao servidas pelo proprio
    # backend, entao o navegador carrega as de verdade e o e2e exercita o que
    # o usuario realmente recebe.
    #
    # Os ladrilhos do mapa continuam cortados: vem da rede por natureza, e
    # desenhar o mapa nao e o que nenhum destes testes verifica.
    contexto.route("**tile.openstreetmap.org/**", lambda rota: rota.abort())

    contexto.add_cookies([{
        'name': 'adri_sessao_local', 'value': TOKEN_E2E_SESSAO_LOCAL,
        'url': servidor, 'sameSite': 'Strict',
    }])

    # `load`, e nao `networkidle`: o Service Worker mantem trafego de fundo, e
    # a pagina nunca fica "ociosa" pelo criterio do Playwright.
    pagina.goto(servidor, wait_until="load")
    pagina.wait_for_selector("#aba-dashboard", timeout=15000)

    # Esperar o DOM nao basta: o app so pede dados DEPOIS de confirmar sessao
    # e licenca, e ate a resposta chegar a lista esta em esqueleto. Um teste
    # que comeca a clicar nesse meio-tempo compete com a carga inicial -- ele
    # cadastra, busca, e a carga que estava em voo repinta a tabela por cima
    # do resultado, deixando o esqueleto na tela no instante da leitura.
    #
    # A falha aparecia como `'Bruno Lima' not in ' 	 	...'`, que nao
    # se parece com um problema de tempo e custa caro para diagnosticar. A
    # janela sempre existiu; ela ficou larga o bastante para doer quando a
    # abertura passou a fazer duas consultas antes de carregar.
    # A condicao precisa de um sinal POSITIVO de que a carga terminou. "Sem
    # esqueleto" nao serve: a tabela comeca VAZIA, sem esqueleto nenhum, e a
    # espera passaria na janela entre o inicio da carga e o desenho do
    # esqueleto. `renderizarTabela` sempre escreve algo -- as linhas, ou o
    # estado vazio -- entao ter filho e nao ter esqueleto e o par que
    # significa "acabou".
    pagina.wait_for_function(
        "() => { const t = document.getElementById('tabelaClientes');"
        " return t && t.children.length > 0"
        " && t.querySelectorAll('tr.skeleton-row').length === 0; }",
        timeout=15000,
    )
    pagina.erros_de_javascript = erros

    yield pagina

    contexto.close()


# =============================================================================
# A pagina carrega sem explodir
# =============================================================================
def test_a_interface_carrega_sem_erro_de_javascript(pagina):
    """
    O teste mais barato e o que mais pega.

    Um `ReferenceError` num arquivo carregado interrompe TUDO que vem depois
    dele -- e o sintoma na tela e apenas "alguns botoes nao funcionam".
    """
    pagina.wait_for_timeout(1200)
    assert pagina.erros_de_javascript == [], \
        f"a pagina levantou erro de JavaScript: {pagina.erros_de_javascript}"


def test_o_dashboard_desenha(pagina):
    pagina.wait_for_selector("#aba-dashboard.active", timeout=5000)
    assert pagina.locator("#tituloPagina").inner_text().strip() == "Dashboard"


# =============================================================================
# Comandos declarativos: o que substituiu os handlers inline
# =============================================================================
def test_nenhum_comando_do_markup_ficou_sem_funcao(pagina):
    """
    A regressao concreta da migracao dos `onclick`.

    O markup pode declarar `data-comando="x"` sem que `x` exista ou esteja na
    lista branca -- e o botao vira decoracao silenciosa. Nenhum teste de
    string acha isso, porque o HTML esta certo.
    """
    problemas = pagina.evaluate("""() => {
        const nomes = [...new Set([...document.querySelectorAll('[data-comando]')]
            .map(el => el.getAttribute('data-comando')))];
        return nomes.filter(n =>
            COMANDOS_PERMITIDOS.indexOf(n) === -1 || typeof window[n] !== 'function');
    }""")
    assert problemas == [], f"comandos sem funcao ou fora da lista branca: {problemas}"


def test_nao_sobrou_handler_inline_na_pagina_montada(pagina):
    """Vale para o HTML servido E para o que o JavaScript monta depois."""
    assert pagina.locator("[onclick]").count() == 0




def test_modal_abre_e_fecha(pagina):
    """
    Ate a 1.4.2 este teste usava o modal de novo recebimento. Aquele modal
    saiu com o modulo financeiro; o de produto exercita o mesmo mecanismo --
    `<dialog>` aberto e fechado por comando declarativo.
    """
    pagina.click('[data-comando="trocarAba"][data-arg="produtos"]')
    pagina.click('[data-comando="abrirFormularioProduto"]')
    pagina.wait_for_selector("#modalProduto[open]", timeout=3000)

    pagina.click('#modalProduto [data-comando="fecharModal"]')
    # `wait_for_selector` espera VISIBILIDADE, e um <dialog> fechado tem
    # display:none -- o seletor nunca ficaria visivel. O que se quer aqui e o
    # atributo, nao a pintura.
    pagina.wait_for_function(
        "() => !document.getElementById('modalProduto').open", timeout=3000
    )


def test_tema_alterna_e_persiste_no_recarregamento(pagina):
    inicial = pagina.evaluate("document.documentElement.getAttribute('data-theme')")
    pagina.click('[data-comando="toggleTheme"]')
    pagina.wait_for_timeout(300)
    alternado = pagina.evaluate("document.documentElement.getAttribute('data-theme')")
    assert alternado != inicial

    pagina.reload(wait_until="load")
    pagina.wait_for_timeout(400)
    assert pagina.evaluate("document.documentElement.getAttribute('data-theme')") == alternado


# =============================================================================
# Um fluxo de negocio inteiro, pela tela
# =============================================================================
def test_cadastrar_cliente_pela_tela_e_ve_lo_na_lista(pagina):
    """
    O caminho mais percorrido do sistema, exercitado como o operador faz:
    preencher o formulario, salvar, e conferir que o registro aparece.
    """
    pagina.click('[data-comando="trocarAba"][data-arg="clientes"]')
    pagina.wait_for_selector("#aba-clientes.active")

    pagina.fill("#nome", "Cliente Ponta a Ponta")
    pagina.fill("#cep", "11000-000")
    pagina.fill("#rua", "Rua do Teste, 123")
    pagina.fill("#bairro", "Centro")
    pagina.fill("#cidade", "Santos")
    pagina.click("#clienteForm button[type=submit]")

    pagina.wait_for_selector("#tabelaClientes:has-text('Cliente Ponta a Ponta')", timeout=8000)
    assert pagina.locator("#tabelaClientes").inner_text().count("Cliente Ponta a Ponta") == 1


def test_busca_filtra_a_lista(pagina):
    pagina.click('[data-comando="trocarAba"][data-arg="clientes"]')
    pagina.wait_for_selector("#aba-clientes.active")

    for nome in ("Ana Souza", "Bruno Lima"):
        pagina.fill("#nome", nome)
        pagina.fill("#cep", "11000-000")
        pagina.fill("#rua", "Rua X")
        pagina.fill("#bairro", "Centro")
        pagina.fill("#cidade", "Santos")
        pagina.click("#clienteForm button[type=submit]")
        pagina.wait_for_selector(f"#tabelaClientes:has-text('{nome}')", timeout=8000)

    pagina.fill("#inputPesquisa", "Bruno")

    # Espera o RESULTADO, e nao o relogio.
    #
    # Aqui havia `wait_for_timeout(900)` para cobrir o debounce da busca: passa
    # na maquina de quem escreveu e falha num runner carregado, lendo o
    # esqueleto de carregamento -- uma tabela de espacos duros, sem nome
    # nenhum.
    #
    # Os TRES fatos precisam valer AO MESMO TEMPO, numa condicao so. Separa-los
    # nao funciona, e o motivo e sutil: "tem Bruno" ja era verdade antes da
    # busca, porque ele acabou de ser cadastrado; e "nao tem Ana" fica
    # verdadeiro no ESQUELETO, que nao tem nome nenhum. Duas esperas em
    # sequencia passam nos estados errados e a leitura cai no meio da
    # repintura.
    pagina.wait_for_function(
        """() => {
            const t = document.getElementById('tabelaClientes');
            if (!t || t.querySelectorAll('tr.skeleton-row').length) return false;
            const texto = t.innerText;
            return texto.includes('Bruno Lima') && !texto.includes('Ana Souza');
        }""",
        timeout=8000,
    )


    tabela = pagina.locator("#tabelaClientes").inner_text()
    assert "Bruno Lima" in tabela
    assert "Ana Souza" not in tabela


# =============================================================================
# Acessibilidade: o minimo verificavel sem ferramenta externa
# =============================================================================
def test_todo_campo_do_formulario_tem_rotulo(pagina):
    """
    Campo sem rotulo e anunciado pelo leitor de tela como "caixa de edicao" e
    nada mais. A inspecao estatica conta `label for=`; aqui a associacao e
    conferida no DOM montado, que e onde ela vale.
    """
    sem_rotulo = pagina.evaluate("""() => {
        const campos = [...document.querySelectorAll(
            '#aba-clientes input:not([type=hidden]):not([type=checkbox]), ' +
            '#aba-clientes select, #aba-clientes textarea')];
        return campos.filter(campo => {
            if (campo.getAttribute('aria-label')) return false;
            if (campo.getAttribute('aria-labelledby')) return false;
            if (campo.id && document.querySelector(`label[for="${campo.id}"]`)) return false;
            return !campo.closest('label');
        }).map(campo => campo.id || campo.name || campo.outerHTML.slice(0, 80));
    }""")
    assert sem_rotulo == [], f"campos sem rotulo: {sem_rotulo}"


def test_as_abas_tem_semantica_de_tablist(pagina):
    pagina.click('[data-comando="trocarAba"][data-arg="clientes"]')
    pagina.wait_for_selector("#aba-clientes.active")

    selecionadas = pagina.evaluate(
        "[...document.querySelectorAll('.nav-tab')]"
        ".filter(t => t.getAttribute('aria-selected') === 'true')"
        ".map(t => t.id)"
    )
    assert selecionadas == ["tab-clientes"], \
        f"deveria haver exatamente uma aba marcada como selecionada: {selecionadas}"


def test_o_foco_do_teclado_e_visivel(pagina):
    """Foco invisivel torna a navegacao por teclado um jogo de adivinhacao."""
    pagina.keyboard.press("Tab")
    contorno = pagina.evaluate("""() => {
        const el = document.activeElement;
        if (!el || el === document.body) return null;
        const estilo = getComputedStyle(el);
        return {
            outline: estilo.outlineStyle + ' ' + estilo.outlineWidth,
            sombra: estilo.boxShadow
        };
    }""")
    assert contorno is not None, "o Tab nao moveu o foco para elemento nenhum"
    tem_indicador = (
        contorno["outline"] not in ("none 0px", "none medium")
        or contorno["sombra"] not in ("none", "")
    )
    assert tem_indicador, f"elemento focado sem indicacao visual: {contorno}"


# =============================================================================
# O app aberto sem conta conectada
#
# A 1.3.1 fechou a leitura da API sem sessao -- correto do lado do servidor, e
# do lado da tela criou um estado que nunca tinha existido. O que o operador
# via nao era um erro: era o Dashboard com "0 Total Clientes" e "R$ 0,00 em
# atraso", numeros que sao os zeros escritos no HTML e nao o cadastro. Quem
# abrisse o app sem ter conectado leria "nada a receber" e acreditaria.
#
# Estes testes fixam as duas metades: a tela nao inventa numero, e a tela nao
# assusta com erro. Ela explica e oferece o caminho.
# =============================================================================
def test_sem_sessao_a_tela_pede_conexao(pagina_sem_sessao):
    tela = pagina_sem_sessao.locator("#telaLogin")
    assert tela.is_visible()
    assert pagina_sem_sessao.locator("#formLoginLocal").is_visible()
    assert pagina_sem_sessao.locator("#localUsername").is_visible()
    assert pagina_sem_sessao.locator("#localSenha").is_visible()
    assert pagina_sem_sessao.locator("#etapaLogin [data-comando=\"abrirCadastroPublico\"]").is_visible()


def test_sem_sessao_nenhum_numero_do_dashboard_aparece(pagina_sem_sessao):
    """
    O ponto do achado. Nao basta o painel existir: o conteudo atras dele
    precisa sumir, senao "R$ 0,00 em atraso" continua legivel -- e continua
    mentindo.
    """
    casca = pagina_sem_sessao.locator("#appShell")
    assert casca.get_attribute("aria-hidden") == "true"
    assert casca.evaluate("el => el.inert") is True


def test_sem_sessao_o_cadastro_nao_vaza_para_a_tela(pagina_sem_sessao):
    """O banco TEM um cliente. Nenhum pedaco dele pode aparecer."""
    assert "Maria Souza" not in pagina_sem_sessao.content()


def test_sem_sessao_nao_aparece_toast_de_erro(pagina_sem_sessao):
    """
    "O app nao pode dar erro algum." Com o painel explicando a situacao, um
    "Erro ao carregar clientes." vermelho por cima e o pior dos dois mundos:
    assusta e nao diz o que fazer.
    """
    pagina_sem_sessao.wait_for_timeout(2500)
    toast = pagina_sem_sessao.locator("#toast")
    if toast.count() and toast.is_visible():
        texto = toast.inner_text().lower()
        assert "erro" not in texto and "falha" not in texto, f"toast de erro: {texto}"


def test_sem_sessao_nao_ha_erro_de_javascript(pagina_sem_sessao):
    pagina_sem_sessao.wait_for_timeout(2000)
    assert pagina_sem_sessao.erros_de_javascript == []


def test_sem_sessao_trocar_de_aba_nao_revela_conteudo(pagina_sem_sessao):
    """Sem sessão, nem o app nem a navegação ficam interativos."""
    assert pagina_sem_sessao.locator("#telaLogin").is_visible()
    assert pagina_sem_sessao.locator("#appShell").evaluate("el => el.inert") is True


def test_com_sessao_o_painel_nao_atrapalha(pagina):
    """A outra direcao: fechar demais seria a mesma regressao ao contrario."""
    painel = pagina.locator("#painelSemConexao")
    assert not painel.is_visible()
    assert not pagina.locator("#telaLogin").is_visible()
    assert pagina.locator("#aba-dashboard").is_visible()


# =============================================================================
# O periodo de teste encerrado
#
# Mesma exigencia do estado sem conexao: a tela nao pode inventar numero nem
# assustar com erro. A diferenca e que aqui existe uma acao que resolve --
# pagar -- e ela precisa estar a um clique, com o valor a vista.
# =============================================================================
def test_licenca_vencida_a_tela_pede_pagamento(pagina_licenca_vencida):
    painel = pagina_licenca_vencida.locator("#telaPagamento")
    assert painel.is_visible()
    assert "Pagamento necessário para continuar. Período de teste encerrado" in painel.inner_text()
    assert "R$ 2.000,00" in painel.inner_text()
    assert "Entre em contato com o fornecedor para efetuar o pagamento" in painel.inner_text()
    assert not pagina_licenca_vencida.locator("#btnGerarPixLicenca").is_visible()


def test_licenca_vencida_nenhum_numero_aparece(pagina_licenca_vencida):
    """Os zeros do HTML sao tao mentirosos aqui quanto no estado sem conexao."""
    assert pagina_licenca_vencida.locator("#appShell").evaluate("el => el.inert") is True


def test_licenca_vencida_o_cadastro_nao_vaza(pagina_licenca_vencida):
    assert "Maria Souza" not in pagina_licenca_vencida.content()


def test_licenca_vencida_nao_carrega_dados_por_tras_do_painel(pagina_licenca_vencida):
    """
    O defeito exato. `checarLoginExistente` chamava o carregamento antes da
    consulta de licenca: as requisicoes voltavam 402 e o app se dava por
    carregado -- entao pagar liberava a tela sem trazer dado nenhum.
    """
    pagina_licenca_vencida.wait_for_timeout(1500)
    estado = pagina_licenca_vencida.evaluate(
        "() => ({ carregados: window._dadosJaCarregados,"
        " vencida: window._licencaVencida,"
        " verificada: window._licencaVerificada })"
    )
    assert estado["vencida"] is True
    assert estado["verificada"] is True
    assert estado["carregados"] is False,         "o app pediu dados com a licenca vencida; ao liberar, nao recarregaria"


def test_licenca_vencida_nao_aparece_toast_de_erro(pagina_licenca_vencida):
    pagina_licenca_vencida.wait_for_timeout(2000)
    toast = pagina_licenca_vencida.locator("#toast")
    if toast.count() and toast.is_visible():
        texto = toast.inner_text().lower()
        assert "erro" not in texto and "falha" not in texto, f"toast de erro: {texto}"


def test_licenca_vencida_nao_ha_erro_de_javascript(pagina_licenca_vencida):
    pagina_licenca_vencida.wait_for_timeout(1500)
    assert pagina_licenca_vencida.erros_de_javascript == []


def test_licenca_vigente_nao_mostra_o_painel(pagina):
    """A direcao oposta: bloquear quem esta em dia seria a regressao inversa."""
    assert not pagina.locator("#telaPagamento").is_visible()
    assert pagina.locator("#aba-dashboard").is_visible()


# =============================================================================
# Identificacao de versao beta
#
# O README, a descricao do repositorio e a pagina de releases ja avisam que
# isto e beta -- mas quem usa o app instalado nunca ve nenhum dos tres. O selo
# fecha essa lacuna no unico lugar onde o operador realmente esta.
# =============================================================================
def test_o_selo_de_beta_aparece_na_interface(pagina):
    selo = pagina.locator("#seloBeta")
    assert selo.is_visible()
    assert selo.inner_text().strip() == "BETA"


def test_o_selo_carrega_a_versao_exata_do_backend(pagina):
    """
    A versao vai no `title`, e nao no texto: o selo precisa caber ao lado da
    marca. E vem de /api/health, que a le do package.json -- se fosse escrita
    a mao no HTML, um dia discordaria da versao real e ninguem perceberia.
    """
    pagina.wait_for_function(
        "() => (document.getElementById('seloBeta')?.title || '').includes('1.')",
        timeout=10000,
    )
    titulo = pagina.locator("#seloBeta").get_attribute("title")
    assert "beta" in titulo.lower(), f"a versao no selo nao indica beta: {titulo}"


def test_a_versao_do_pacote_declara_pre_lancamento():
    """
    O sufixo `-beta` no package.json e o que faz o instalador sair como
    `AdriPoltronasSetup-1.4.0-beta.exe` e a sonda /api/health reportar beta.
    Sem ele, o aviso viveria so na documentacao e o artefato entregue diria
    que e uma versao final.
    """
    import json
    caminho = os.path.join(RAIZ, "package.json")
    with open(caminho, encoding="utf-8") as arquivo:
        versao = json.load(arquivo)["version"]
    assert "-beta" in versao, f"package.json declara {versao}, sem marca de pre-lancamento"


# =============================================================================
# A conexao com a Microsoft na topbar
#
# Ela vivia no rodape da aba Clientes, longe do indicador de rede -- duas
# informacoes da mesma natureza ("como este app esta ligado ao mundo") em
# lugares distantes, e a da conta so era encontrada por quem ja sabia que
# existia.
# =============================================================================
def test_o_botao_de_conexao_fica_na_topbar(pagina):
    botao = pagina.locator("#btnConectarMicrosoft")
    assert botao.is_visible()
    assert botao.evaluate("el => !!el.closest('.topbar-acoes')"),         "o botao saiu da topbar"


def test_o_botao_de_conexao_fica_ao_lado_do_estado_da_rede(pagina):
    """Lado a lado, e na mesma altura: alturas diferentes os fariam parecer
    dois controles sem relacao."""
    medidas = pagina.evaluate("""() => {
        const b = document.getElementById('btnConectarMicrosoft').getBoundingClientRect();
        const o = document.getElementById('onlineStatus').getBoundingClientRect();
        return { desalinhamento: Math.abs(b.top - o.top),
                 diferencaDeAltura: Math.abs(b.height - o.height) };
    }""")
    assert medidas["desalinhamento"] < 2
    assert medidas["diferencaDeAltura"] < 2


def test_conectado_o_botao_mostra_a_conta_e_o_title_traz_o_endereco(pagina):
    """
    O espaco na topbar e curto: o rotulo leva o essencial e o `title` leva o
    resto. A fixture semeia `operador@exemplo.local`.
    """
    pagina.wait_for_function(
        "() => document.getElementById('btnConectarMicrosoft')"
        ".classList.contains('conectado')",
        timeout=10000,
    )
    botao = pagina.locator("#btnConectarMicrosoft")
    assert botao.inner_text().strip() == "MS: operador"
    assert "operador@exemplo.local" in botao.get_attribute("title")


def test_o_rodape_de_clientes_mantem_as_acoes_que_sao_dele(pagina):
    """Mover a conexao nao podia levar junto o que opera sobre a lista: o
    envio ao Excel usa a selecao de clientes, e backup e restauracao sao
    acoes da tela, nao do estado da conexao."""
    pagina.click('[data-comando="trocarAba"][data-arg="clientes"]')
    pagina.wait_for_selector("#aba-clientes.active")
    for identificador in ("btnEnviarExcel", "btnBackupBanco", "btnRestaurarBanco"):
        assert pagina.locator("#" + identificador).count() == 1, identificador


# =============================================================================
# Consentimento do mapa (SEG-05)
# =============================================================================
def test_o_mapa_nao_consulta_o_nominatim_sem_autorizacao(pagina):
    """
    A propriedade que importa: abrir a aba Mapa NAO pode disparar consulta
    nenhuma ao Nominatim.

    Ate a 1.5.0 o endereco completo de cada cliente ativo -- rua, bairro,
    cidade e CEP -- saia para um servico fora do pais no instante em que a aba
    era aberta. Havia aviso na tela, e o aviso era claro; o que nao havia era
    como recusar.

    O teste conta REQUISICOES, e nao o que a tela mostra: esconder o mapa e
    consultar assim mesmo passaria numa verificacao visual.
    """
    consultas = []
    pagina.context.route(
        "**nominatim.openstreetmap.org/**",
        lambda rota: (consultas.append(rota.request.url),
                      rota.fulfill(status=200, content_type="application/json", body="[]")),
    )

    pagina.click('[data-comando="trocarAba"][data-arg="mapa"]')
    pagina.wait_for_selector("#mapaConsentimento", state="visible", timeout=10000)
    pagina.wait_for_timeout(1500)

    assert consultas == [], f"endereco enviado sem autorizacao: {consultas}"
    assert pagina.is_hidden("#mapaClientes")


def test_autorizar_libera_o_mapa_e_o_estado_persiste(pagina):
    """
    O outro lado: autorizar tem de funcionar de verdade, e a resposta nao pode
    ser perguntada de novo a cada troca de aba.
    """
    pagina.context.route(
        "**nominatim.openstreetmap.org/**",
        lambda rota: rota.fulfill(
            status=200, content_type="application/json",
            body='[{"lat": "-26.30", "lon": "-48.84"}]'),
    )

    pagina.click('[data-comando="trocarAba"][data-arg="mapa"]')
    pagina.wait_for_selector("#mapaConsentimento", state="visible", timeout=10000)
    pagina.click('[data-comando="autorizarMapa"]')

    pagina.wait_for_selector("#mapaClientes", state="visible", timeout=10000)
    assert pagina.is_hidden("#mapaConsentimento")
    # As ações de apagar/revogar são restritas ao perfil de desenvolvedor.
    assert pagina.is_hidden("#mapaControles")

    # Sai da aba e volta: o pedido nao pode reaparecer.
    pagina.click('[data-comando="trocarAba"][data-arg="dashboard"]')
    pagina.click('[data-comando="trocarAba"][data-arg="mapa"]')
    pagina.wait_for_timeout(500)
    assert pagina.is_hidden("#mapaConsentimento")


def test_revogar_apaga_as_coordenadas_guardadas(pagina):
    """
    Revogar sem apagar deixaria as coordenadas de todos os clientes guardadas
    numa maquina onde o operador acabou de dizer que nao quer isso.
    """
    # O cache e semeado direto, e nao geocodificando de verdade: a fila real
    # respeita 1,1 s por cliente para nao estourar o limite do Nominatim, e
    # atravessa-la aqui tornaria o teste lento e instavel sem medir mais nada.
    # O que se afirma e o efeito de revogar sobre o que ESTA guardado.
    pagina.evaluate(
        "localStorage.setItem('adri-geocache',"
        " JSON.stringify({'rua x,centro,joinville': [-26.30, -48.84]}));"
        "localStorage.setItem('adri-mapa-consentimento:1', 'sim');"
    )
    pagina.reload(wait_until="load")
    pagina.click('[data-comando="trocarAba"][data-arg="mapa"]')
    pagina.wait_for_selector("#mapaClientes", state="visible", timeout=10000)

    assert pagina.is_hidden("#mapaControles")
    assert pagina.evaluate("localStorage.getItem('adri-geocache')") is not None
    assert pagina.evaluate("localStorage.getItem('adri-mapa-consentimento:1')") == 'sim'


def test_apagar_coordenadas_nao_revoga_a_autorizacao(pagina):
    """
    Sao duas acoes distintas de proposito: apagar o cache resolve coordenada
    errada, e continuar autorizado e o que o operador espera nesse caso. Juntar
    as duas obrigaria a reautorizar por causa de um endereco que mudou.
    """
    pagina.evaluate(
        "localStorage.setItem('adri-geocache',"
        " JSON.stringify({'rua x,centro,joinville': [-26.30, -48.84]}));"
        "localStorage.setItem('adri-mapa-consentimento:1', 'sim');"
    )
    pagina.reload(wait_until="load")
    pagina.click('[data-comando="trocarAba"][data-arg="mapa"]')
    pagina.wait_for_selector("#mapaClientes", state="visible", timeout=10000)

    assert pagina.is_hidden("#mapaControles")
    assert pagina.evaluate("localStorage.getItem('adri-geocache')") is not None
    assert pagina.evaluate("localStorage.getItem('adri-mapa-consentimento:1')") == 'sim'
    assert pagina.is_hidden("#mapaConsentimento")
