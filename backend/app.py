import logging
import os
import secrets
from logging.handlers import RotatingFileHandler
import uuid
import json
import sys
import hmac
from flask import (
    Flask,
    g,
    request,
    jsonify,
    send_from_directory,
    render_template,
    render_template_string,
)
from werkzeug.exceptions import HTTPException
from flask_limiter.util import get_remote_address

import database
import config
import security
import microsoft
import capacidade
import licenca
import licenca_remota
from limites import limiter
from erp.core.contexto import (
    ContextoOperacao,
    anonimizar_ip,
    encerrar_contexto,
    iniciar_contexto,
)

LOG_DIR = os.path.join(os.environ.get("APPDATA", os.getcwd()), "AdriPoltronas", "logs")

# Rotacao: 5 arquivos de 2 MB.
#
# O `FileHandler` anterior escrevia num unico `app.log` que crescia sem limite.
# Numa instalacao que roda todo dia por anos isso vira um arquivo de centenas
# de megabytes -- inutil para depurar (ninguem abre) e desagradavel de ter na
# pasta do usuario. Com rotacao, os ultimos 10 MB ficam sempre disponiveis e o
# resto sai sozinho.
TAMANHO_MAXIMO_LOG = 2 * 1024 * 1024
ARQUIVOS_DE_LOG_MANTIDOS = 5

try:
    os.makedirs(LOG_DIR, exist_ok=True)
    _log_path = os.path.join(LOG_DIR, "app.log")
    _arquivo = RotatingFileHandler(
        _log_path,
        maxBytes=TAMANHO_MAXIMO_LOG,
        backupCount=ARQUIVOS_DE_LOG_MANTIDOS,
        encoding="utf-8",
    )
    _handlers = [_arquivo, logging.StreamHandler(sys.stderr)]
except OSError:
    _handlers = [logging.StreamHandler(sys.stderr)]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=_handlers,
)
log = logging.getLogger("adri.app")

# Garante que exista um .env preenchivel em %APPDATA%. Sem isso o app
# instalado (Program Files, sem escrita) nao tinha onde receber credenciais.
_ENV_DO_USUARIO = config.garantir_modelo_env() or '(indisponivel)'


def _avisar_configuracao_pendente() -> None:
    """Registra, no boot, o que esta faltando e onde corrigir."""
    if not config.GEMINI_API_KEY:
        log.warning("GEMINI_API_KEY nao definida. Sugestao de bairro via IA desabilitada. "
                    "Defina em %s", _ENV_DO_USUARIO)

    # A licenca so consegue cobrar se souber falar com o Mercado Pago. Sem o
    # token, o bloqueio dos 30 dias continua valendo e nao ha como pagar por
    # dentro do aplicativo -- que e um estado pior do que nao ter licenca.
    import mercadopago
    if not mercadopago.esta_configurado():
        log.warning("MP_ACCESS_TOKEN nao definido. A licenca nao podera ser paga "
                    "pelo aplicativo. Ver LICENCA_E_PAGAMENTO.md")


_avisar_configuracao_pendente()

diretorio_atual = os.path.dirname(os.path.abspath(__file__))
if diretorio_atual not in sys.path:
    sys.path.append(diretorio_atual)

if getattr(sys, 'frozen', False):
    RAIZ_RECURSOS = sys._MEIPASS
    PASTA_FRONTEND = os.path.join(RAIZ_RECURSOS, 'frontend')
    PASTA_TEMPLATES = os.path.join(RAIZ_RECURSOS, 'templates')
else:
    PASTA_FRONTEND = os.path.abspath(os.path.join(diretorio_atual, '..', 'frontend'))
    PASTA_TEMPLATES = os.path.join(diretorio_atual, 'templates')

app = Flask(__name__,
    static_folder=PASTA_FRONTEND,
    static_url_path='',
    template_folder=PASTA_TEMPLATES,
)

# ---------------------------------------------------------------------------
# SESSION COOKIE SEGURO
# ---------------------------------------------------------------------------
app.secret_key = os.environ.get('ADRI_FLASK_SECRET')
if not app.secret_key:
    if getattr(sys, 'frozen', False):
        log.warning("ADRI_FLASK_SECRET nao definida. Usando chave temporaria.")
        security.log_evento_seguro("SECRET_GERADO", "ADRI_FLASK_SECRET nao definida, gerando chave temporaria", "warning")
    app.secret_key = secrets.token_hex(32)

app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=False,
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_NAME='adri_session',
    PERMANENT_SESSION_LIFETIME=28800,
    MAX_CONTENT_LENGTH=10 * 1024 * 1024,
    SEND_FILE_MAX_AGE_DEFAULT=0,
    TEMPLATES_AUTO_RELOAD=True,
    PRESERVE_CONTEXT_ON_EXCEPTION=False,
    EXPLAIN_TEMPLATE_LOADING=False,
)

# ENV='production' vivia nesta lista e nao fazia nada: o Flask removeu a
# chave ENV na 2.3 (aqui roda a 3.1), entao era so uma entrada inerte no
# dicionario de config sugerindo um modo que ninguem le.

# ---------------------------------------------------------------------------
# O TOKEN CSRF SAIU NA 1.5.1
#
# Havia aqui um cache que gerava um token e o devolvia no header X-CSRF-Token
# a cada resposta. O frontend guardava em cookie e reenviava. E o backend nunca
# validava, em lugar nenhum -- as duas pontas executavam o ritual completo de
# uma protecao inexistente.
#
# Quem protege as rotas que alteram estado e `_bloquear_requisicao_de_origem_
# externa`, pela checagem de Origin/Referer, e sempre foi.
#
# Ligar a validacao de verdade nao era alternativa: a chave do cache era o
# cookie `adri_session`, que este app nunca emite (havia UMA entrada, de chave
# vazia, para todo mundo), e `security.validar_csrf_token` era de uso unico
# enquanto o cache reservava o mesmo token por uma hora -- a segunda requisicao
# seria recusada como replay.
#
# Se um dia fizer sentido ter CSRF de verdade aqui, ele nasce inteiro: emissao
# por sessao real, validacao no `before_request`, e teste que falhe sem ela.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# RATE LIMITING
# ---------------------------------------------------------------------------
# O objeto vive em `limites.py` para que os blueprints possam apertar as
# proprias rotas sem importar `app` de volta. Ver aquele modulo para o que o
# limite defende e o que nao defende.
limiter.init_app(app)


@limiter.request_filter
def _sem_limite_em_testes():
    """
    Em TESTING o limitador nao conta, pelo mesmo motivo que a capacidade e a
    autenticacao nao valem: a suite roda centenas de requisicoes em segundos,
    de um IP so, e bateria em qualquer teto realista. Um teste falharia por
    429 sem relacao com o que ele mede, e a falha apareceria em arquivos
    diferentes conforme a ordem de execucao.

    Os limites de verdade sao exercitados por test_limites.py, que desliga o
    modo -- mesma solucao adotada em test_autenticacao.py.
    """
    return bool(app.config.get('TESTING'))


# ---------------------------------------------------------------------------
# CONTENT SECURITY POLICY
# ---------------------------------------------------------------------------
def _csp_header() -> str:
    """
    Politica de seguranca de conteudo aplicada a todas as respostas.

    `script-src` NAO libera mais 'unsafe-inline'. Ate a versao 1.1 liberava,
    porque o index.html carregava 36 handlers `onclick=` -- e essa liberacao
    nao e seletiva: ela vale para TODO script inline da pagina, inclusive um
    que viesse a ser injetado por um campo de cadastro mal escapado. Com os
    handlers substituidos por acoes declarativas (`data-acao`, despachadas por
    um registro em app.js), a politica passa a recusar script inline por
    completo.

    `style-src` mantem 'unsafe-inline', e nao e descuido: o Leaflet e o Chart.js
    posicionam elementos escrevendo no atributo `style` em tempo de execucao.
    Sem a liberacao, o mapa e os graficos param de desenhar. Estilo injetado
    permite defacement e vazamento por seletor, nao execucao de codigo -- e a
    troca, aqui, e consciente.
    """
    # `script-src 'self'` sem excecao: o Leaflet e o Chart.js passaram a ser
    # servidos pelo proprio backend (frontend/vendor/). Enquanto vinham de CDN,
    # a politica precisava confiar em unpkg.com e cdn.jsdelivr.net -- dois
    # dominios de terceiro autorizados a executar codigo dentro do app, num
    # programa que trata nome, endereco e valores a receber dos clientes.
    return "; ".join([
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
        "font-src 'self' https://fonts.gstatic.com",
        # openstreetmap.org continua liberado: sao os ladrilhos do mapa, que por
        # natureza vem da rede. As IMAGENS do Leaflet (marcador, sombra) agora
        # sao locais e cabem em 'self'.
        "img-src 'self' data: blob: https://*.tile.openstreetmap.org",
        "connect-src 'self' https://viacep.com.br https://nominatim.openstreetmap.org https://generativelanguage.googleapis.com https://login.microsoftonline.com",
        "frame-ancestors 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "block-all-mixed-content",
        "upgrade-insecure-requests",
    ])


_METODOS_QUE_ALTERAM_ESTADO = frozenset({'POST', 'PUT', 'PATCH', 'DELETE'})

# Todas as rotas da API são locais. As únicas exceções de capacidade são o
# callback OAuth e a sonda de identidade; nenhuma devolve dados de negócio.
ALIASES_LOOPBACK = config.ALIASES_LOOPBACK


def _origens_aceitas() -> set:
    host = request.host
    aceitas = {f'http://{host}', f'https://{host}'}
    nome, separador, porta = host.partition(':')
    if nome in ALIASES_LOOPBACK:
        sufixo = f':{porta}' if separador else ''
        for alias in ALIASES_LOOPBACK:
            aceitas.add(f'http://{alias}{sufixo}')
            aceitas.add(f'https://{alias}{sufixo}')
    return aceitas


# ---------------------------------------------------------------------------
# HOST DE LOOPBACK
# ---------------------------------------------------------------------------
# `_origens_aceitas()` monta a lista de origens validas a partir do proprio
# header `Host`, que quem chama controla. Isso e circular: um cliente que
# envia `Host: mal.exemplo` junto com `Origin: http://mal.exemplo` passa na
# checagem comparando a mentira dele com ela mesma. E o vetor classico de DNS
# rebinding contra servico em loopback -- basta um dominio que resolva para
# 127.0.0.1 para o navegador do usuario emprestar a origem.
#
# O que se fixa aqui e o NOME do host, nao a porta. O nome e o que o atacante
# precisa controlar para montar o ataque, e o conjunto legitimo tem tres
# elementos conhecidos. A porta continua livre porque o proprio frontend seria
# recusado se o servidor subisse em outra -- e a suite ja cobre esse caso.


def _nome_do_host(host: str) -> str:
    """Host sem a porta. Trata `[::1]:5000`, que um split ingenuo por ':' parte
    no lugar errado."""
    host = (host or '').strip().lower()
    if host.startswith('['):
        fecha = host.find(']')
        return host[:fecha + 1] if fecha != -1 else host
    return host.partition(':')[0]


@app.before_request
def _exigir_host_de_loopback():
    if _nome_do_host(request.host) in config.ALIASES_LOOPBACK:
        return None
    log.warning("[SEGURANCA] Host recusado: %s -> %s", request.host, request.path)
    security.log_evento_seguro(
        "HOST_REJEITADO", f"Host: {request.host}, Path: {request.path}", "warning"
    )
    return jsonify({"erro": "Host nao permitido."}), 400


# ---------------------------------------------------------------------------
# CAPACIDADE DE ACESSO
# ---------------------------------------------------------------------------
@app.before_request
def _exigir_capacidade():
    """
    Fecha a API para quem nao e o aplicativo.

    Loopback nao e privado: qualquer processo da maquina, e qualquer pagina
    aberta no navegador do usuario, alcanca 127.0.0.1:5000. Ate aqui um
    `GET /api/clientes` sem cabecalho nenhum devolvia a lista completa de
    clientes -- nome, endereco e CEP.

    Ver `capacidade.py` para o desenho e para o limite honesto da protecao.
    """
    if app.config.get('TESTING') or not capacidade.esta_ativa():
        return None
    if request.path in capacidade.ROTAS_ISENTAS:
        return None
    if capacidade.confere(capacidade.apresentado_em(request.headers, request.cookies)):
        return None

    log.warning("[CAPACIDADE] Requisicao sem token: %s %s", request.method, request.path)
    security.log_evento_seguro(
        "CAPACIDADE_AUSENTE", f"{request.method} {request.path}", "warning"
    )
    return jsonify({"erro": "Acesso negado."}), 403


@app.after_request
def _semear_cookie_de_capacidade(resposta):
    """
    Converte o cabecalho aceito num cookie de mesma origem.

    O Electron injeta o cabecalho na sessao da janela, o que cobre navegacao,
    fetch e XHR. O cookie cobre o resto -- em especial o Service Worker, que
    reencaminha um `Request` ja montado pela pagina e que, dependendo do
    caminho, nao passa pela injecao.

    HttpOnly para script nenhum conseguir ler; SameSite=Strict para nenhuma
    outra origem conseguir provocar o envio.

    Em TESTING nao semeia, pelo mesmo motivo que `_exigir_capacidade` nao
    exige: a suite nao carrega token. Antes isto era implicito -- sem a
    variavel de ambiente, `esta_ativa()` devolvia False e a funcao caia fora
    sozinha. Agora que a exigencia e sempre ligada, a isencao precisa estar
    escrita.
    """
    if app.config.get('TESTING') or not capacidade.esta_ativa():
        return resposta
    if not capacidade.confere(request.headers.get(capacidade.NOME_DO_HEADER)):
        return resposta
    if request.cookies.get(capacidade.NOME_DO_COOKIE):
        return resposta
    resposta.set_cookie(
        capacidade.NOME_DO_COOKIE,
        capacidade.token_esperado(),
        httponly=True,
        samesite='Strict',
        secure=False,  # a origem e http://127.0.0.1; Secure impediria o envio
        path='/',
    )
    return resposta


# ---------------------------------------------------------------------------
# SONDA DE IDENTIDADE
# ---------------------------------------------------------------------------
@app.route('/api/health')
def health():
    """
    Diz QUEM esta atendendo na porta, e se aceita a capacidade apresentada.

    Existe por causa de um comportamento do Electron: ele reaproveitava
    qualquer servidor que respondesse em 5000, sem verificar que servidor era.
    Um processo alheio na porta herdava a janela do aplicativo -- e tudo o que
    ela mandasse.

    Nao exige capacidade, de proposito: e justamente a rota que permite
    descobrir se a capacidade em maos serve. Nao devolve dado de negocio.
    """
    apresentado = capacidade.apresentado_em(request.headers, request.cookies)
    return jsonify({
        "servico": "adri-poltronas",
        "versao": config.VERSAO_DO_APP,
        "capacidade_exigida": capacidade.esta_ativa(),
        "capacidade_aceita": (not capacidade.esta_ativa()) or capacidade.confere(apresentado),
    })


# ---------------------------------------------------------------------------
# ANTI-VAZAMENTO DE INFORMACAO - Handler de erro que nunca expoe detalhes internos
# ---------------------------------------------------------------------------
@app.errorhandler(Exception)
def _erro_generico(e):
    if request.path.startswith('/api/'):
        # Aqui a excecao MORRE: o operador recebe um 500 sem detalhe interno e
        # o id de correlacao e a unica ponte entre a tela e o log. Por isso o
        # traceback tem de ser registrado neste ponto, com o id junto.
        correlation_id = uuid.uuid4().hex[:12]
        log.exception("Erro nao tratado [%s]: %s", correlation_id, e)
        return jsonify({"erro": "Erro interno do servidor.", "id": correlation_id}), 500

    # Fora de /api/ a excecao SEGUE, para o Flask renderizar a pagina de erro
    # HTML. E o Flask registra o traceback dela por conta propria, no
    # `app.logger`.
    #
    # Registrar aqui tambem gravava o MESMO traceback duas vezes em `app.log`,
    # com ids de correlacao diferentes e nenhum deles exibido a ninguem -- o
    # que faz o arquivo parecer contar dois incidentes onde houve um. Uma linha
    # curta basta para dizer que a excecao passou por aqui.
    log.warning("Excecao fora de /api/ em %s: %s", request.path, type(e).__name__)
    raise e


@app.errorhandler(HTTPException)
def _erro_http(e):
    if request.path.startswith('/api/'):
        return jsonify({"erro": e.description or e.name}), e.code
    return e


# ---------------------------------------------------------------------------
# AUTH MIDDLEWARE - Verifica sessao em TODA a API
# ---------------------------------------------------------------------------
# Cada rota desta lista responde antes de existir sessao, e por um motivo:
#
#   /api/auth/login, /api/auth/status, /api/auth/logout, /callback
#       -- sao o proprio fluxo de login. Exigir sessao neles seria pedir a
#          chave para entregar a chave.
#   /api/health -- e a sonda de identidade. O Electron e o app Qt perguntam a
#          ela QUEM esta na porta antes de adotar o backend, e isso acontece
#          muito antes de qualquer login. Nao devolve dado de negocio.
#   /, /manifest.json, /sw.js -- a interface que precisa carregar antes de
#          o operador escolher se quer entrar com uma conta.
ROTAS_SEM_AUTH = frozenset({
    '/api/auth/login', '/api/auth/status', '/api/auth/logout',
    '/api/auth/local/login', '/api/auth/local/status',
    '/api/auth/local/register', '/api/auth/local/setup',
    '/api/auth/local/me',
    '/api/health',
    '/', '/manifest.json', '/sw.js',
    '/callback',
})


def _verificar_autenticacao():
    """Exige uma sessão local para toda API que não seja de autenticação."""
    if app.config.get('TESTING'):
        return None

    if request.path in ROTAS_SEM_AUTH:
        return None

    if request.method == 'GET' and not request.path.startswith('/api/'):
        return None

    sessao_info = _obter_sessao_valida()
    if sessao_info:
        sessao = sessao_info['dados']
        username = sessao.get('username', '')
        user_id = sessao.get('user_id')
        usuario_local = database.obter_usuario_por_id(user_id) if user_id else None
        if not usuario_local or not usuario_local.get('ativo'):
            database.excluir_sessao_local()
            return jsonify({"erro": "Esta conta foi desativada.", "codigo": "conta_inativa"}), 401
        g.erp_usuario_identificador = username
        g.erp_usuario_role = usuario_local.get('role', 'usuario')
        g.erp_usuario_id = usuario_local.get('id')
        return None

    if request.method == 'OPTIONS':
        return None

    log.warning("[AUTH] Requisicao sem login local bloqueada: %s %s", request.method, request.path)
    return jsonify({
        "erro": "Entre com uma conta local para acessar o sistema.",
        "codigo": "autenticacao_necessaria",
    }), 401

def _obter_sessao_valida():
    """Confere a sessão persistida contra o cookie HttpOnly do cliente."""
    sessao_local = database.obter_sessao_local()
    token_cookie = request.cookies.get(database.NOME_COOKIE_SESSAO_LOCAL, '')
    token_salvo = (sessao_local or {}).get('token', '')
    if (
        token_cookie
        and token_salvo
        and hmac.compare_digest(token_cookie, token_salvo)
    ):
        return {'tipo': 'local', 'dados': sessao_local}
    return None


# ---------------------------------------------------------------------------
# BEFORE REQUEST - Todas as verificacoes de seguranca
# ---------------------------------------------------------------------------
@app.before_request
def _bloquear_requisicao_de_origem_externa():
    if request.method not in _METODOS_QUE_ALTERAM_ESTADO:
        return None
    if not request.path.startswith('/api/'):
        return None
    aceitas = _origens_aceitas()

    origem = request.headers.get('Origin')
    if origem is not None:
        if origem not in aceitas:
            log.warning("[CSRF] Origin recusada: %s -> %s", origem, request.path)
            security.log_evento_seguro("CSRF_ORIGEM_REJEITADA", f"Origin: {origem}, Path: {request.path}", "warning")
            return jsonify({"erro": "Origem nao permitida."}), 403
        return None

    referer = request.headers.get('Referer')
    if referer is not None:
        if not any(referer == o or referer.startswith(o + '/') for o in aceitas):
            log.warning("[CSRF] Referer recusado: %s -> %s", referer, request.path)
            security.log_evento_seguro("CSRF_REFERER_REJEITADO", f"Referer: {referer}, Path: {request.path}", "warning")
            return jsonify({"erro": "Origem nao permitida."}), 403

    return None


@app.before_request
def _aplicar_seguranca_requisicao():
    """Seguranca adicional por requisicao."""
    resposta_auth = _verificar_autenticacao()
    if resposta_auth is not None:
        return resposta_auth

    # A checagem de forca bruta que existia aqui saiu na 1.5.1. Ela estava
    # inerte: nenhum ponto do backend chamava `registrar_tentativa_login`,
    # entao o contador nunca saia do zero e a funcao sempre devolvia False.
    # Nao ha login com senha neste app -- a autenticacao e o OAuth da
    # Microsoft --, entao nao havia o que contar. Um guarda que sempre deixa
    # passar nao e defesa em profundidade: e uma linha que faz o leitor
    # acreditar numa protecao a mais do que existe.

    ua = request.headers.get('User-Agent', '')
    if ua and any(b in ua.lower() for b in ['sqlmap', 'nikto', 'nmap', 'masscan', 'zgrab']):
        log.warning("[SECURITY] User-Agent bloqueado: %s", ua[:50])
        security.log_evento_seguro("BLOQUEIO_UA_MALICIOSO", f"User-Agent: {ua[:100]}", "warning")
        return jsonify({"erro": "Acesso negado."}), 403

    return None


# ---------------------------------------------------------------------------
# LICENCA DE USO
# ---------------------------------------------------------------------------
# O acesso de contas comuns usa o periodo de teste gravado por usuario; uma
# licenca paga da instalacao libera todas as contas. O desenvolvedor pode
# acessar o painel para controlar cada periodo.
#
# Este guarda roda DEPOIS do de sessao, de proposito: quem nao esta autenticado
# no app nao precisa saber em que pe esta a licenca dele. E responde 402
# (Payment Required), e nao 403, porque o codigo aqui carrega informacao util
# -- a interface distingue "pague" de "conecte-se" so pelo status.
ROTAS_SEM_LICENCA = frozenset({
    '/api/health', '/api/auth/login', '/api/auth/status', '/api/auth/logout',
    '/api/auth/local/register', '/api/auth/local/setup', '/api/auth/local/usuarios',
    '/callback',
}) | licenca.ROTAS_ISENTAS


@app.before_request
def _exigir_licenca():
    if app.config.get('TESTING'):
        return None
    if not request.path.startswith('/api/'):
        return None
    if request.path in ROTAS_SEM_LICENCA:
        return None
    if request.path.startswith('/api/auth/local/'):
        return None
    role = getattr(g, 'erp_usuario_role', '')
    if role == 'desenvolvedor':
        return None

    if licenca.situacao()['estado'] == licenca.ESTADO_PAGA:
        return None
    user_id = getattr(g, 'erp_usuario_id', None)
    if user_id and licenca_remota.api_configurada():
        remota = licenca_remota.situacao_em_cache(user_id)
        if remota:
            if remota['estado'] in (licenca.ESTADO_TESTE, licenca.ESTADO_PAGA, licenca.ESTADO_DESATIVADA):
                return None
            situacao = remota
            log.warning("[LICENCA] Requisição bloqueada pela licença central: %s %s",
                        request.method, request.path)
            return jsonify({"erro": "Período de teste encerrado.", "licenca": situacao}), 402
    situacao = licenca.situacao_usuario(user_id) if user_id else licenca.situacao()
    if situacao['estado'] in (licenca.ESTADO_TESTE, licenca.ESTADO_PAGA, licenca.ESTADO_DESATIVADA):
        return None
    log.warning("[LICENCA] Requisicao bloqueada, licenca %s: %s %s",
                situacao['estado'], request.method, request.path)
    return jsonify({
        "erro": "Periodo de teste encerrado.",
        "licenca": situacao,
    }), 402


@app.before_request
def _iniciar_contexto_operacao():
    """Propaga identidade tecnica e correlacao para servicos de dominio."""
    correlation_recebido = (request.headers.get('X-Correlation-ID') or '').strip()
    caracteres_validos = set(
        "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.:"
    )
    if (
        not correlation_recebido
        or len(correlation_recebido) > 64
        or any(c not in caracteres_validos for c in correlation_recebido)
    ):
        correlation_recebido = uuid.uuid4().hex

    origem = 'api_local'
    contexto = ContextoOperacao(
        origem=origem,
        correlation_id=correlation_recebido,
        usuario_identificador=getattr(g, 'erp_usuario_identificador', ''),
        usuario_role=getattr(g, 'erp_usuario_role', ''),
        ip_hash=anonimizar_ip(get_remote_address(), str(app.secret_key)),
        rota=request.path,
        metodo=request.method,
    )
    g.erp_correlation_id = correlation_recebido
    g.erp_contexto_token = iniciar_contexto(contexto)


@app.teardown_request
def _encerrar_contexto_operacao(_erro):
    token = getattr(g, 'erp_contexto_token', None)
    if token is not None:
        encerrar_contexto(token)


@app.after_request
def _aplicar_cabecalhos_de_seguranca(resposta):
    resposta.headers.setdefault('Content-Security-Policy', _csp_header())
    resposta.headers.setdefault('X-Content-Type-Options', 'nosniff')
    resposta.headers.setdefault('X-Frame-Options', 'DENY')
    resposta.headers.setdefault('Referrer-Policy', 'no-referrer')
    resposta.headers.setdefault('X-XSS-Protection', '0')
    resposta.headers.setdefault('Cache-Control', 'no-store, no-cache, must-revalidate, proxy-revalidate')
    resposta.headers.setdefault('Pragma', 'no-cache')
    resposta.headers.setdefault('Expires', '0')
    resposta.headers.setdefault('Strict-Transport-Security', 'max-age=31536000; includeSubDomains')
    resposta.headers.setdefault('Permissions-Policy', 'geolocation=(), microphone=(), camera=(), payment=()')
    resposta.headers['X-Content-Type-Options'] = 'nosniff'
    resposta.headers['X-Frame-Options'] = 'DENY'
    correlation_id = getattr(g, 'erp_correlation_id', '')
    if correlation_id:
        resposta.headers.setdefault('X-Correlation-ID', correlation_id)
    return resposta



# ---------------------------------------------------------------------------
# ROTA INDEX
# ---------------------------------------------------------------------------
@app.route('/')
def index():
    return render_template('index.html')


@app.route('/callback')
def auth_callback():
    import urllib.request
    import urllib.parse
    import urllib.error

    code = request.args.get('code')
    state_recebido = request.args.get('state', '')
    log.info("[CALLBACK] Retorno OAuth recebido.")

    if not code:
        return render_template_string(config._CALLBACK_TEMPLATE, titulo="Erro na autenticacao", erro=True,
            mensagem="Codigo de autorizacao ausente.", instrucao="Feche esta aba e tente novamente."), 400

    dados_pendentes = config._oauth_pending.pop(state_recebido, None) if state_recebido else None
    if not dados_pendentes:
        log.warning("[CALLBACK] Estado OAuth ausente, inválido ou expirado.")
        return render_template_string(config._CALLBACK_TEMPLATE, titulo="Erro de seguranca", erro=True,
            mensagem="Sessao de login invalida ou expirada.", instrucao="Feche esta aba e reinicie o login."), 400

    code_verifier = dados_pendentes['verifier']
    # Os escopos aqui precisam bater com os pedidos em /api/auth/login, senao
    # a Microsoft recusa a troca. Por isso os dois leem a mesma constante.
    payload = {
        'client_id': config.CLIENT_ID, 'scope': config.ESCOPOS_MICROSOFT, 'code': code,
        'redirect_uri': config.REDIRECT_URI, 'grant_type': 'authorization_code', 'code_verifier': code_verifier,
    }
    data = urllib.parse.urlencode(payload).encode('utf-8')

    try:
        with urllib.request.urlopen(urllib.request.Request(config.URL_TOKEN_MICROSOFT, data=data, method='POST'), timeout=15) as resposta:  # noqa: S310 - URL montada de constante do proprio codigo, sempre https
            res_dados = json.loads(resposta.read().decode('utf-8'))
            token_acesso = res_dados.get('access_token')

            req_perfil = urllib.request.Request("https://graph.microsoft.com/v1.0/me",
                headers={"Authorization": f"Bearer {token_acesso}"})
            with urllib.request.urlopen(req_perfil, timeout=15) as resp_perfil:  # noqa: S310 - URL montada de constante do proprio codigo, sempre https
                dados_perfil = json.loads(resp_perfil.read().decode('utf-8'))
                email_usuario = dados_perfil.get('userPrincipalName', 'Conta Conectada')

            # A allowlist e conferida ANTES de gravar a sessao: uma conta nao
            # autorizada nunca chega a existir na tabela. Recusar depois, no
            # guarda de autenticacao, deixaria a linha gravada e o operador
            # legitimo desconectado -- `salvar_sessao` substitui a sessao
            # anterior.
            if not config.conta_autorizada(email_usuario):
                log.warning("[CALLBACK] Conta fora da allowlist recusada.")
                security.log_evento_seguro(
                    "OAUTH_CONTA_RECUSADA", "Conta Microsoft nao autorizada", "warning")
                if request.headers.get('Accept') == 'application/json':
                    return jsonify({
                        "erro": "Esta conta nao tem permissao para usar o sistema.",
                        "codigo": "conta_nao_autorizada",
                    }), 403
                return render_template_string(
                    config._CALLBACK_TEMPLATE, titulo="Conta nao autorizada", erro=True,
                    mensagem=f"A conta {email_usuario} nao tem permissao para usar este sistema.",
                    instrucao="Feche esta aba e entre com a conta autorizada."), 403

            # `refresh_token` so vem porque `offline_access` esta nos escopos.
            # E ele que evita mandar o operador refazer o login a cada hora.
            role = config.obter_role(email_usuario)
            database.salvar_sessao(
                token_acesso,
                email_usuario,
                refresh_token=res_dados.get('refresh_token'),
                expira_em=microsoft.calcular_expiracao(res_dados.get('expires_in')),
                role=role,
            )
            security.log_evento_seguro("OAUTH_LOGIN", "Login Microsoft realizado")
            return render_template_string(config._CALLBACK_TEMPLATE, titulo="Autenticacao Concluida com Sucesso!",
                mensagem="Credenciais registradas com seguranca.", instrucao=f"Conta: {email_usuario}")
    except urllib.error.HTTPError as e:
        log.error("OAuth HTTPError: código HTTP %s.", e.code)
        return render_template_string(config._CALLBACK_TEMPLATE, titulo="Erro na autenticacao", erro=True,
            mensagem="Nao foi possivel obter token.", instrucao="Tente novamente."), 400
    except Exception as e:
        log.exception("OAuth erro: %s", e)
        return render_template_string(config._CALLBACK_TEMPLATE, titulo="Erro na autenticacao", erro=True,
            mensagem="Erro ao processar credenciais.", instrucao="Tente novamente."), 500


@app.route('/manifest.json')
def manifest():
    return send_from_directory(app.static_folder, 'manifest.json')


@app.route('/sw.js')
def service_worker():
    return send_from_directory(app.static_folder, 'sw.js')


# ---------------------------------------------------------------------------
# Import blueprints no fim do modulo
# ---------------------------------------------------------------------------
from blueprints import (  # noqa: E402
    auth_bp, auth_local_bp, clientes_bp,
    ia_bp, entregas_bp, dashboard_bp, notificacoes_bp, excel_bp,
    produtos_bp, pedidos_bp, backup_bp, licenca_bp
)

app.register_blueprint(auth_bp)
app.register_blueprint(auth_local_bp)
app.register_blueprint(clientes_bp)
app.register_blueprint(ia_bp)
app.register_blueprint(entregas_bp)
app.register_blueprint(dashboard_bp)
app.register_blueprint(notificacoes_bp)
app.register_blueprint(excel_bp)
app.register_blueprint(produtos_bp)
app.register_blueprint(pedidos_bp)
app.register_blueprint(backup_bp)
app.register_blueprint(licenca_bp)


if __name__ == '__main__':
    database.criar_tabela()
    app.run(host='localhost', port=5000)
