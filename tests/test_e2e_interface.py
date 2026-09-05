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
import os
import socket
import subprocess
import sys
import time

import pytest

playwright_api = pytest.importorskip(
    "playwright.sync_api",
    reason="Playwright nao instalado. Ver o cabecalho deste arquivo.",
)
sync_playwright = playwright_api.sync_playwright

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
BACKEND = os.path.join(RAIZ, 'backend')

TIMEOUT_BOOT_S = 40


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
    Grava uma sessao Microsoft no banco de teste.

    Nao e conveniencia: sem ela, POST/PUT/DELETE em /api/* respondem 401. A
    autenticacao do ERP e o OAuth da Microsoft -- conceitualmente errado, e
    documentado como pendencia em CONTRIBUTING.md --, entao criar cliente
    exige estar "conectado ao OneDrive". Um teste ponta a ponta que ignorasse
    isso nao exercitaria o fluxo do operador; exercitaria um sistema em que
    ninguem consegue cadastrar nada.
    """
    sys.path.insert(0, BACKEND)
    import database

    original = database.DB_PATH
    database.DB_PATH = str(caminho_do_banco)
    try:
        database.criar_tabela()
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
def _backend_no_ar(banco):
    """Sobe o backend real sobre `banco` e devolve a URL base."""
    porta = _porta_livre()

    ambiente = {
        **os.environ,
        'ADRI_DB_PATH': str(banco),
        'ADRI_PORTA': str(porta),
        'PYTHONUNBUFFERED': '1',
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
            [sys.executable, os.path.join(BACKEND, 'servidor.py')],
            cwd=BACKEND, env=ambiente,
            stdout=saida, stderr=subprocess.STDOUT, text=True,
        )

        base = f"http://127.0.0.1:{porta}"
        limite = time.time() + TIMEOUT_BOOT_S
        while time.time() < limite:
            if processo.poll() is not None:
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
            pytest.fail(f"o backend nao respondeu em {TIMEOUT_BOOT_S}s")

        try:
            yield base
        finally:
            processo.terminate()
            try:
                processo.wait(timeout=5)
            except subprocess.TimeoutExpired:
                processo.kill()


@pytest.fixture(scope="module")
def servidor(tmp_path_factory):
    """Backend com sessao Microsoft gravada: o app em uso normal."""
    banco = tmp_path_factory.mktemp("e2e") / "e2e.db"
    _semear_sessao(banco)
    with _backend_no_ar(banco) as base:
        yield base


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
    """Contexto novo, com os CDNs neutralizados."""
    contexto = navegador.new_context()

    # Leaflet e Chart.js vem de CDN. Numa maquina sem internet -- ou num
    # runner de CI com saida restrita -- esperar por eles trava o teste em
    # algo que nao e o objeto do teste.
    def _script_vazio(rota):
        rota.fulfill(status=200, content_type="application/javascript", body="")

    contexto.route("**unpkg.com/**", _script_vazio)
    contexto.route("**cdn.jsdelivr.net/**", _script_vazio)
    contexto.route("**tile.openstreetmap.org/**", lambda rota: rota.abort())
    return contexto


@pytest.fixture
def pagina_sem_sessao(navegador, servidor_sem_sessao):
    """A tela de quem abre o app sem nunca ter conectado a conta."""
    contexto = _preparar_contexto(navegador)
    pagina = contexto.new_page()

    erros = []
    pagina.on("pageerror", lambda erro: erros.append(str(erro)))

    pagina.goto(servidor_sem_sessao, wait_until="load")
    # `state="attached"`, e nao visivel: as abas continuam no DOM e e o CSS
    # que as esconde enquanto o painel esta na tela. Esperar por visibilidade
    # aqui daria timeout justamente quando o comportamento esta CERTO.
    pagina.wait_for_selector("#aba-dashboard", state="attached", timeout=15000)
    pagina.wait_for_selector("#painelSemConexao", timeout=15000)
    pagina.erros_de_javascript = erros

    yield pagina

    contexto.close()


@pytest.fixture
def pagina(navegador, servidor):
    contexto = navegador.new_context()
    pagina = contexto.new_page()

    erros = []
    pagina.on("pageerror", lambda erro: erros.append(str(erro)))

    # Leaflet e Chart.js vem de CDN. Numa maquina sem internet -- ou num
    # runner de CI com saida restrita -- esperar por eles trava o teste em
    # algo que nao e o objeto do teste. Sao respondidos com um script vazio:
    # o que se exercita aqui e o codigo do aplicativo.
    def _script_vazio(rota):
        rota.fulfill(status=200, content_type="application/javascript", body="")

    contexto.route("**unpkg.com/**", _script_vazio)
    contexto.route("**cdn.jsdelivr.net/**", _script_vazio)
    contexto.route("**tile.openstreetmap.org/**", lambda rota: rota.abort())

    # `load`, e nao `networkidle`: o Service Worker mantem trafego de fundo, e
    # a pagina nunca fica "ociosa" pelo criterio do Playwright.
    pagina.goto(servidor, wait_until="load")
    pagina.wait_for_selector("#aba-dashboard", timeout=15000)
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


@pytest.mark.parametrize("aba", [
    "clientes", "pedidos", "produtos", "entregas", "mapa",
    "pagamentos", "relatorios", "dashboard",
])
def test_cada_aba_abre_ao_clicar(pagina, aba):
    """Clique de verdade, e nao chamada direta da funcao: o caminho que o
    operador percorre inclui o despachante delegado."""
    pagina.click(f'[data-comando="trocarAba"][data-arg="{aba}"]')
    pagina.wait_for_selector(f"#aba-{aba}.active", timeout=5000)
    assert pagina.locator(f"#aba-{aba}").is_visible()


def test_modal_abre_e_fecha(pagina):
    pagina.click('[data-comando="trocarAba"][data-arg="pagamentos"]')
    pagina.click('[data-comando="abrirModalNovoRecebimento"]')
    pagina.wait_for_selector("#modalNovoRecebimento[open]", timeout=3000)

    pagina.click('[data-comando="fecharModalNovoRecebimento"]')
    # `wait_for_selector` espera VISIBILIDADE, e um <dialog> fechado tem
    # display:none -- o seletor nunca ficaria visivel. O que se quer aqui e o
    # atributo, nao a pintura.
    pagina.wait_for_function(
        "() => !document.getElementById('modalNovoRecebimento').open", timeout=3000
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
    pagina.wait_for_timeout(900)  # a busca e debounced

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
    painel = pagina_sem_sessao.locator("#painelSemConexao")
    assert painel.is_visible()
    assert "Conecte sua conta Microsoft" in painel.inner_text()
    assert pagina_sem_sessao.locator("#btnConectarPeloPainel").is_visible()


def test_sem_sessao_nenhum_numero_do_dashboard_aparece(pagina_sem_sessao):
    """
    O ponto do achado. Nao basta o painel existir: o conteudo atras dele
    precisa sumir, senao "R$ 0,00 em atraso" continua legivel -- e continua
    mentindo.
    """
    for identificador in ("metricTotalClientes", "metricEntregas", "metricRetiradas"):
        elemento = pagina_sem_sessao.locator("#" + identificador)
        if elemento.count():
            assert not elemento.is_visible(), f"{identificador} visivel sem sessao"

    assert not pagina_sem_sessao.locator("#aba-dashboard").is_visible()


def test_sem_sessao_o_cadastro_nao_vaza_para_a_tela(pagina_sem_sessao):
    """O banco TEM um cliente. Nenhum pedaco dele pode aparecer."""
    assert "Maria Souza" not in pagina_sem_sessao.content()


def test_sem_sessao_nao_aparece_toast_de_erro(pagina_sem_sessao):
    """
    "O app nao pode dar erro algum." Com o painel explicando a situacao, um
    "Erro ao carregar pagamentos." vermelho por cima e o pior dos dois mundos:
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
    """O painel vale para o app inteiro, e nao so para a aba de abertura."""
    for aba in ("clientes", "pagamentos", "entregas"):
        pagina_sem_sessao.click(f'[data-comando="trocarAba"][data-arg="{aba}"]')
        pagina_sem_sessao.wait_for_timeout(300)
        assert pagina_sem_sessao.locator("#painelSemConexao").is_visible()
        assert not pagina_sem_sessao.locator(f"#aba-{aba}").is_visible()


def test_com_sessao_o_painel_nao_atrapalha(pagina):
    """A outra direcao: fechar demais seria a mesma regressao ao contrario."""
    painel = pagina.locator("#painelSemConexao")
    assert not painel.is_visible()
    assert pagina.locator("#aba-dashboard").is_visible()
