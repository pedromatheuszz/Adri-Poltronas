import logging
import os
import secrets
import uuid
import json
import sys
import time
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
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

import database
import config
import security
import asaas
import microsoft
import capacidade
from erp.core.contexto import (
    ContextoOperacao,
    anonimizar_ip,
    encerrar_contexto,
    iniciar_contexto,
)

LOG_DIR = os.path.join(os.environ.get("APPDATA", os.getcwd()), "AdriPoltronas", "logs")
try:
    os.makedirs(LOG_DIR, exist_ok=True)
    _log_path = os.path.join(LOG_DIR, "app.log")
    _handlers = [logging.FileHandler(_log_path, encoding="utf-8"), logging.StreamHandler(sys.stderr)]
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

    # Checagem contra o proprio modulo asaas (e nao contra config) para que o
    # aviso reflita o que a integracao realmente enxerga em tempo de execucao.
    if not asaas.esta_configurado():
        log.warning("ASAAS_API_KEY nao definida. Pagamentos online desabilitados. "
                    "Defina em %s", _ENV_DO_USUARIO)
    elif asaas.chave_incompativel_com_ambiente():
        log.warning("ASAAS_API_KEY nao corresponde ao ambiente '%s'. "
                    "Toda cobranca vai falhar com 401. Revise ASAAS_SANDBOX em %s",
                    asaas.ambiente(), _ENV_DO_USUARIO)

    if not config.ASAAS_WEBHOOK_TOKEN:
        log.warning("ASAAS_WEBHOOK_TOKEN nao definido. Webhook de pagamentos recusara "
                    "requisicoes. Defina em %s", _ENV_DO_USUARIO)


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
# CSRF TOKEN global para a sessao
# ---------------------------------------------------------------------------
VALIDADE_CSRF_SEGUNDOS = 3600
MAX_TOKENS_CSRF_EM_CACHE = 1000

_csrf_token_cache = {}


def _obter_csrf_token() -> str:
    """
    Retorna ou gera o token enviado no header X-CSRF-Token.

    ATENCAO -- o backend NAO valida este token em lugar nenhum. Quem
    protege as rotas que alteram estado e a checagem de Origin/Referer em
    _bloquear_requisicao_de_origem_externa(), como descreve o
    API_STANDARD.md. O header existe porque o frontend faz a outra metade
    do ritual (guarda em cookie e reenvia), e some-lo quebraria essa ponta.

    Duas consequencias de nao ser um token de verdade, para nao induzir a
    erro quem for mexer aqui:
      - a chave do cache e o cookie `adri_session`, que este app nunca
        emite. Na pratica ha uma unica entrada, de chave '', para todos.
      - security.validar_csrf_token() e de uso unico (marca `usado`),
        enquanto este cache reserve o MESMO token por uma hora. Ligar uma
        coisa na outra hoje recusaria a segunda requisicao como replay.
    """
    session_id = request.cookies.get('adri_session', '')
    if session_id in _csrf_token_cache:
        token_info = _csrf_token_cache[session_id]
        if time.time() - token_info['gerado_em'] < VALIDADE_CSRF_SEGUNDOS:
            return token_info['token']
    token = security.gerar_csrf_token()
    _csrf_token_cache[session_id] = {'token': token, 'gerado_em': time.time()}
    if len(_csrf_token_cache) > MAX_TOKENS_CSRF_EM_CACHE:
        limpar_csrf_cache()
    return token


def limpar_csrf_cache():
    """Remove do cache os tokens CSRF ja expirados."""
    agora = time.time()
    # As entradas vivas sao copiadas ANTES do clear(). Reconstruir lendo do
    # proprio dicionario ja esvaziado levantava KeyError e derrubava a
    # requisicao que tivesse a infelicidade de estourar o limite do cache.
    vivos = {chave: dados for chave, dados in _csrf_token_cache.items()
             if agora - dados['gerado_em'] < VALIDADE_CSRF_SEGUNDOS}
    _csrf_token_cache.clear()
    _csrf_token_cache.update(vivos)


# ---------------------------------------------------------------------------
# RATE LIMITING
# ---------------------------------------------------------------------------
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per minute", "50 per second"],
    storage_uri="memory://",
)


# ---------------------------------------------------------------------------
# CONTENT SECURITY POLICY
# ---------------------------------------------------------------------------
def _csp_header() -> str:
    """
    Politica de seguranca de conteudo aplicada a todas as respostas.

    'unsafe-inline' em script-src segue necessario enquanto o index.html usar
    handlers `onclick=` inline (sao 22 hoje). Um nonce seria mais forte, mas
    precisa ser gerado por requisicao E injetado no template -- gera-lo no
    after_request, sem repassa-lo ao HTML, bloquearia todo script inline da
    pagina, ou seja, a interface inteira. Ate os handlers sairem do markup, o
    que a politica de fato restringe e DE ONDE script/estilo/dados podem vir,
    que e o vetor que importa num app servido em loopback.
    """
    return "; ".join([
        "default-src 'self'",
        "script-src 'self' 'unsafe-inline' https://unpkg.com https://cdn.jsdelivr.net",
        "style-src 'self' 'unsafe-inline' https://unpkg.com https://fonts.googleapis.com",
        "font-src 'self' https://fonts.gstatic.com",
        "img-src 'self' data: blob: https://*.tile.openstreetmap.org https://unpkg.com",
        "connect-src 'self' https://viacep.com.br https://nominatim.openstreetmap.org https://generativelanguage.googleapis.com https://login.microsoftonline.com",
        "frame-ancestors 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "block-all-mixed-content",
        "upgrade-insecure-requests",
    ])


_METODOS_QUE_ALTERAM_ESTADO = frozenset({'POST', 'PUT', 'PATCH', 'DELETE'})

ROTAS_SEM_CHECAGEM_DE_ORIGEM = frozenset({'/api/pagamentos/webhook'})

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
    """
    if not capacidade.esta_ativa():
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
    correlation_id = uuid.uuid4().hex[:12]
    log.exception("Erro nao tratado [%s]: %s", correlation_id, e)
    if request.path.startswith('/api/'):
        return jsonify({"erro": "Erro interno do servidor.", "id": correlation_id}), 500
    raise e


@app.errorhandler(HTTPException)
def _erro_http(e):
    if request.path.startswith('/api/'):
        return jsonify({"erro": e.description or e.name}), e.code
    return e


# ---------------------------------------------------------------------------
# AUTH MIDDLEWARE - Verifica sessao em rotas que alteram estado
# ---------------------------------------------------------------------------
ROTAS_SEM_AUTH = frozenset({
    '/api/auth/login', '/api/auth/status', '/api/auth/logout',
    '/', '/manifest.json', '/sw.js',
    '/callback', '/api/pagamentos/webhook',
})


def _verificar_autenticacao():
    """
    Verifica se o usuario esta autenticado antes de operacoes que alteram estado.
    Em modo TESTING, permite todas as requisicoes para manter compatibilidade com testes.
    """
    if app.config.get('TESTING'):
        return None

    if request.path in ROTAS_SEM_AUTH:
        return None

    if request.method == 'GET' and not request.path.startswith('/api/'):
        return None

    sessao = database.obter_sessao()
    if sessao and sessao.get('token'):
        g.erp_usuario_identificador = sessao.get('conta', '')
        return None

    if request.path.startswith('/api/') and request.method not in ('GET', 'OPTIONS'):
        log.warning("[AUTH] Requisicao sem sessao bloqueada: %s %s", request.method, request.path)
        security.log_evento_seguro("AUTH_BLOQUEIO", f"Sem sessao: {request.method} {request.path}", "warning")
        return jsonify({"erro": "Autenticacao necessaria."}), 401

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
    if request.path in ROTAS_SEM_CHECAGEM_DE_ORIGEM:
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

    ip_remoto = get_remote_address()
    # ATENCAO -- esta checagem esta inerte: nenhum ponto do backend chama
    # security.registrar_tentativa_login(), entao o contador nunca sai do
    # zero e isto sempre devolve False. Nao existe login com senha aqui (a
    # autenticacao e OAuth da Microsoft), entao nao ha o que contar hoje.
    # Fica no lugar para o dia em que houver -- mas nao conte com ele como
    # protecao ativa.
    if security.esta_bloqueado_bruteforce(ip_remoto):
        log.warning("[BRUTE-FORCE] IP bloqueado: %s", ip_remoto)
        return jsonify({"erro": "Acesso temporariamente bloqueado por seguranca."}), 429

    ua = request.headers.get('User-Agent', '')
    if ua and any(b in ua.lower() for b in ['sqlmap', 'nikto', 'nmap', 'masscan', 'zgrab']):
        log.warning("[SECURITY] User-Agent bloqueado: %s", ua[:50])
        security.log_evento_seguro("BLOQUEIO_UA_MALICIOSO", f"User-Agent: {ua[:100]}", "warning")
        return jsonify({"erro": "Acesso negado."}), 403

    return None


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

    origem = 'asaas_webhook' if request.path == '/api/pagamentos/webhook' else 'api_local'
    contexto = ContextoOperacao(
        origem=origem,
        correlation_id=correlation_recebido,
        usuario_identificador=getattr(g, 'erp_usuario_identificador', ''),
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


@app.after_request
def _adicionar_csrf_token_header(resposta):
    resposta.headers.setdefault('X-CSRF-Token', _obter_csrf_token())
    return resposta


# ---------------------------------------------------------------------------
# ROTA INDEX
# ---------------------------------------------------------------------------
@app.route('/')
def index():
    m = database.obter_metricas_dashboard()
    total = m['total_clientes'] or 1
    pct = round(((m['cadastros_30d'] or 0) / total) * 100)
    return render_template('index.html',
        TOTAL=m['total_clientes'],
        ENTREGAS=m['total_entrega'],
        RETIRADAS=m['total_retirada'],
        NOVOS=pct,
    )


@app.route('/callback')
def auth_callback():
    import urllib.request
    import urllib.parse
    import urllib.error

    code = request.args.get('code')
    state_recebido = request.args.get('state', '')
    log.info("[CALLBACK] state=%s, code=%s...", state_recebido, (code or '')[:8])

    if not code:
        return render_template_string(config._CALLBACK_TEMPLATE, titulo="Erro na autenticacao", erro=True,
            mensagem="Codigo de autorizacao ausente.", instrucao="Feche esta aba e tente novamente."), 400

    dados_pendentes = config._oauth_pending.pop(state_recebido, None) if state_recebido else None
    if not dados_pendentes:
        log.warning("[CALLBACK] state '%s' not found.", state_recebido)
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
        with urllib.request.urlopen(urllib.request.Request(config.URL_TOKEN_MICROSOFT, data=data, method='POST')) as resposta:
            res_dados = json.loads(resposta.read().decode('utf-8'))
            token_acesso = res_dados.get('access_token')

            req_perfil = urllib.request.Request("https://graph.microsoft.com/v1.0/me",
                headers={"Authorization": f"Bearer {token_acesso}"})
            with urllib.request.urlopen(req_perfil) as resp_perfil:
                dados_perfil = json.loads(resp_perfil.read().decode('utf-8'))
                email_usuario = dados_perfil.get('userPrincipalName', 'Conta Conectada')

            # `refresh_token` so vem porque `offline_access` esta nos escopos.
            # E ele que evita mandar o operador refazer o login a cada hora.
            database.salvar_sessao(
                token_acesso,
                email_usuario,
                refresh_token=res_dados.get('refresh_token'),
                expira_em=microsoft.calcular_expiracao(res_dados.get('expires_in')),
            )
            security.log_evento_seguro("OAUTH_LOGIN", f"Login realizado: {email_usuario}")
            return render_template_string(config._CALLBACK_TEMPLATE, titulo="Autenticacao Concluida com Sucesso!",
                mensagem="Credenciais registradas com seguranca.", instrucao=f"Conta: {email_usuario}")
    except urllib.error.HTTPError as e:
        log.error("OAuth HTTPError: %s %s", e.code, e.read().decode('utf-8', errors='replace'))
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
    auth_bp, clientes_bp, pagamentos_bp, webhook_bp, relatorios_bp,
    ia_bp, entregas_bp, dashboard_bp, notificacoes_bp, excel_bp,
    produtos_bp, pedidos_bp
)

app.register_blueprint(auth_bp)
app.register_blueprint(clientes_bp)
app.register_blueprint(pagamentos_bp)
app.register_blueprint(webhook_bp)
app.register_blueprint(relatorios_bp)
app.register_blueprint(ia_bp)
app.register_blueprint(entregas_bp)
app.register_blueprint(dashboard_bp)
app.register_blueprint(notificacoes_bp)
app.register_blueprint(excel_bp)
app.register_blueprint(produtos_bp)
app.register_blueprint(pedidos_bp)


if __name__ == '__main__':
    database.criar_tabela()
    app.run(host='localhost', port=5000)
