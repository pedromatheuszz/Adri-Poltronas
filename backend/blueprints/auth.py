# backend/blueprints/auth.py
"""Blueprint de autenticação OAuth Microsoft."""
import time
import secrets
import base64
import hashlib
import urllib.parse
import urllib.request
import webbrowser
import logging
from flask import Blueprint, jsonify

import database
import config
import microsoft

log = logging.getLogger("adri.auth")

auth_bp = Blueprint('auth', __name__, url_prefix='/api/auth')


def _gerar_code_verifier() -> str:
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b'=').decode('ascii')


def _derivar_code_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode('ascii')).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b'=').decode('ascii')


@auth_bp.route('/login')
def auth_login():
    agora = time.time()
    chaves_antigas = [k for k, v in config._oauth_pending.items() if agora - v.get('ts', 0) > 300]
    for k in chaves_antigas:
        config._oauth_pending.pop(k, None)

    code_verifier = _gerar_code_verifier()
    code_challenge = _derivar_code_challenge(code_verifier)
    state = secrets.token_urlsafe(16)
    config._oauth_pending[state] = {'verifier': code_verifier, 'ts': agora}
    log.info("[LOGIN] state=%s", state)

    url = (
        f"{config.URL_AUTORIZACAO_MICROSOFT}"
        f"?client_id={config.CLIENT_ID}&response_type=code&redirect_uri={config.REDIRECT_URI}"
        f"&response_mode=query&scope={urllib.parse.quote(config.ESCOPOS_MICROSOFT)}"
        f"&code_challenge={code_challenge}&code_challenge_method=S256"
        f"&state={urllib.parse.quote(state)}"
    )
    webbrowser.open(url)
    return jsonify({"mensagem": "Navegador aberto"})


@auth_bp.route('/status')
def auth_status():
    """
    Estado real da conexao, e nao apenas "existe linha na tabela".

    `obter_token_valido()` renova em silencio quando o token venceu e derruba
    a sessao quando nao ha como renovar. E o que permite a tela so mostrar
    "Conectado" quando exportar de fato vai funcionar -- antes ela afirmava
    isso com base numa linha que podia guardar um token morto ha horas.
    """
    sessao = database.obter_sessao()
    if not sessao:
        return jsonify({"logado": False})

    # A allowlist e conferida aqui tambem, e nao so no guarda de `/api/`.
    #
    # Esta rota esta em ROTAS_SEM_AUTH -- precisa estar, e a tela consulta
    # justamente para saber se ha sessao --, entao `_verificar_autenticacao`
    # retorna antes de rodar e leva `conta_autorizada` junto. Sem esta
    # checagem, uma sessao gravada antes de a allowlist passar a valer fazia a
    # tela anunciar "Conectado (fulano)" e a primeira requisicao de dados
    # recusar aquela mesma conta. O app dizia o contrario do que ia fazer.
    if not config.conta_autorizada(sessao.get("conta", "")):
        return jsonify({"logado": False, "motivo": "conta_nao_autorizada"})

    if microsoft.obter_token_valido() is None:
        return jsonify({"logado": False, "motivo": "sessao_expirada"})

    return jsonify({"logado": True, "conta": sessao["conta"]})


@auth_bp.route('/logout', methods=['POST'])
def auth_logout():
    database.excluir_sessao()
    return jsonify({"mensagem": "Sessao encerrada."})