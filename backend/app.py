import logging
import os
import secrets
import hashlib
import base64
import uuid
import json
import sys
import time
import hmac
from flask import (
    Flask,
    request,
    jsonify,
    send_from_directory,
    render_template,
    render_template_string,
)
from werkzeug.exceptions import HTTPException
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from dotenv import load_dotenv

import database
import validators
import asaas
import config

load_dotenv()

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

diretorio_atual = os.path.dirname(os.path.abspath(__file__))
if diretorio_atual not in sys.path:
    sys.path.append(diretorio_atual)

PASTA_FRONTEND = os.path.abspath(os.path.join(diretorio_atual, '..', 'frontend'))
app = Flask(__name__,
    static_folder=PASTA_FRONTEND,
    static_url_path='',
    template_folder=os.path.join(diretorio_atual, 'templates'),
)
app.secret_key = os.environ.get('ADRI_FLASK_SECRET')
if not app.secret_key:
    if getattr(sys, 'frozen', False):
        log.warning("ADRI_FLASK_SECRET nao definida. Usando chave temporaria.")
    app.secret_key = secrets.token_hex(32)

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per minute", "50 per second"],
    storage_uri="memory://",
)

if not config.GEMINI_API_KEY:
    log.warning("GEMINI_API_KEY nao definida. Sugestao de bairro via IA desabilitada.")

if not config.ASAAS_API_KEY:
    log.warning("ASAAS_API_KEY nao definida. Pagamentos online desabilitados.")


@app.errorhandler(HTTPException)
def _erro_http(e):
    if request.path.startswith('/api/'):
        return jsonify({"erro": e.description or e.name}), e.code
    return e


@app.errorhandler(Exception)
def _erro_generico(e):
    correlation_id = uuid.uuid4().hex[:12]
    log.exception("Erro nao tratado [%s]: %s", correlation_id, e)
    if request.path.startswith('/api/'):
        return jsonify({"erro": "Erro interno do servidor.", "id": correlation_id}), 500
    raise e


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
        NOW=time.strftime('%d/%m/%Y %H:%M'),
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
        return render_template_string(config._CALLBACK_TEMPLATE, titulo="Erro na autenticacao",
            mensagem="Codigo de autorizacao ausente.", instrucao="Feche esta aba e tente novamente."), 400

    dados_pendentes = config._oauth_pending.pop(state_recebido, None) if state_recebido else None
    if not dados_pendentes:
        log.warning("[CALLBACK] state '%s' not found.", state_recebido)
        return render_template_string(config._CALLBACK_TEMPLATE, titulo="Erro de seguranca",
            mensagem="Sessao de login invalida ou expirada.", instrucao="Feche esta aba e reinicie o login."), 400

    code_verifier = dados_pendentes['verifier']
    url_token = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
    payload = {
        'client_id': config.CLIENT_ID, 'scope': 'User.Read Files.ReadWrite', 'code': code,
        'redirect_uri': config.REDIRECT_URI, 'grant_type': 'authorization_code', 'code_verifier': code_verifier,
    }
    data = urllib.parse.urlencode(payload).encode('utf-8')

    try:
        with urllib.request.urlopen(urllib.request.Request(url_token, data=data, method='POST')) as resposta:
            res_dados = json.loads(resposta.read().decode('utf-8'))
            token_acesso = res_dados.get('access_token')

            req_perfil = urllib.request.Request("https://graph.microsoft.com/v1.0/me",
                headers={"Authorization": f"Bearer {token_acesso}"})
            with urllib.request.urlopen(req_perfil) as resp_perfil:
                dados_perfil = json.loads(resp_perfil.read().decode('utf-8'))
                email_usuario = dados_perfil.get('userPrincipalName', 'Conta Conectada')

            database.salvar_sessao(token_acesso, email_usuario)
            return render_template_string(config._CALLBACK_TEMPLATE, titulo="Autenticacao Concluida com Sucesso!",
                mensagem="Credenciais registradas com seguranca.", instrucao=f"Conta: {email_usuario}")
    except urllib.error.HTTPError as e:
        log.error("OAuth HTTPError: %s %s", e.code, e.read().decode('utf-8', errors='replace'))
        return render_template_string(config._CALLBACK_TEMPLATE, titulo="Erro na autenticacao",
            mensagem="Nao foi possivel obter token.", instrucao="Tente novamente."), 400
    except Exception as e:
        log.exception("OAuth erro: %s", e)
        return render_template_string(config._CALLBACK_TEMPLATE, titulo="Erro na autenticacao",
            mensagem="Erro ao processar credenciais.", instrucao="Tente novamente."), 500


@app.route('/manifest.json')
def manifest():
    return send_from_directory(app.static_folder, 'manifest.json')


@app.route('/sw.js')
def service_worker():
    return send_from_directory(app.static_folder, 'sw.js')


from blueprints import (
    auth_bp, clientes_bp, pagamentos_bp, webhook_bp, relatorios_bp,
    ia_bp, entregas_bp, dashboard_bp, notificacoes_bp, excel_bp
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


if __name__ == '__main__':
    database.criar_tabela()
    app.run(host='localhost', port=5000)