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

    scopes = "User.Read Files.ReadWrite"
    url = (
        f"https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
        f"?client_id={config.CLIENT_ID}&response_type=code&redirect_uri={config.REDIRECT_URI}"
        f"&response_mode=query&scope={urllib.parse.quote(scopes)}"
        f"&code_challenge={code_challenge}&code_challenge_method=S256"
        f"&state={urllib.parse.quote(state)}"
    )
    webbrowser.open(url)
    return jsonify({"mensagem": "Navegador aberto"})


@auth_bp.route('/status')
def auth_status():
    sessao = database.obter_sessao()
    if sessao:
        return jsonify({"logado": True, "conta": sessao["conta"]})
    return jsonify({"logado": False})


@auth_bp.route('/logout', methods=['POST'])
def auth_logout():
    database.excluir_sessao()
    return jsonify({"mensagem": "Sessao encerrada."})