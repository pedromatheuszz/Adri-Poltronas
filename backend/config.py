# backend/config.py
"""Configurações compartilhadas entre blueprints e app."""
import sys
import os
import logging
from dotenv import load_dotenv

import segredos

log = logging.getLogger("adri.config")

# Modelo gravado em %APPDATA% na primeira execucao, para que o app instalado
# tenha um lugar previsivel onde receber credenciais.
_MODELO_ENV = """# Configuracao do Adri Poltronas.
# Este arquivo fica fora da pasta de instalacao de proposito: Program Files
# nao e gravavel pelo usuario, e uma atualizacao do app sobrescreveria tudo.

# Chave de assinatura de sessao do Flask.
# Gere com: python -c "import secrets; print(secrets.token_hex(32))"
ADRI_FLASK_SECRET=

# IA - Gemini (fallback de sugestao de bairro quando o ViaCEP falha).
GEMINI_API_KEY=

# Licenca de uso - Mercado Pago.
# Access Token da SUA aplicacao (nao a Public Key). Ver
# LICENCA_E_PAGAMENTO.md para como grava-lo sem passar por arquivo de texto.
MP_ACCESS_TOKEN=
"""


def caminho_env_do_usuario() -> str:
    """
    Caminho do .env do usuario: %APPDATA%/AdriPoltronas/.env.

    Mesma pasta que ja abriga o banco e os logs. `load_dotenv()` sozinho
    resolve a partir do CWD, que no app instalado e Program Files -- pasta sem
    escrita para o usuario e sem .env nenhum. O executavel era entregue sem
    nenhuma forma suportada de configurar MP_ACCESS_TOKEN ou GEMINI_API_KEY, e as
    integracoes nasciam desligadas.
    """
    appdata = os.environ.get('APPDATA')
    if not appdata:
        return ''
    return os.path.join(appdata, 'AdriPoltronas', '.env')


def garantir_modelo_env() -> str:
    """
    Cria o .env do usuario com o modelo comentado, se ainda nao existir.

    Idempotente e nunca destrutivo: um arquivo ja preenchido e mantido como
    esta. Retorna o caminho, ou '' se nao houver onde gravar.
    """
    caminho = caminho_env_do_usuario()
    if not caminho:
        return ''
    if os.path.exists(caminho):
        return caminho
    try:
        os.makedirs(os.path.dirname(caminho), exist_ok=True)
        with open(caminho, 'w', encoding='utf-8') as arquivo:
            arquivo.write(_MODELO_ENV)
        log.info("Modelo de configuracao criado em %s", caminho)
    except OSError as erro:
        log.warning("Nao foi possivel criar %s: %s", caminho, erro)
        return ''
    return caminho


def carregar_configuracao() -> None:
    """
    Carrega o .env do CWD e depois o do usuario.

    A ordem define a precedencia: `load_dotenv` nao sobrescreve variaveis ja
    definidas, entao o .env do repositorio (desenvolvimento) vence, e o de
    %APPDATA% cobre o app instalado.

    Ao final, anota QUAIS nomes vieram de arquivo. E o que permite ao cofre
    saber se uma credencial em `os.environ` foi lida do `.env` -- e portanto
    perde para a versao cifrada -- ou injetada de fora, caso em que vence.
    """
    antes = set(os.environ)

    load_dotenv()
    caminho_usuario = caminho_env_do_usuario()
    if caminho_usuario and os.path.exists(caminho_usuario):
        load_dotenv(caminho_usuario)

    segredos.registrar_origem_env(set(os.environ) - antes)


carregar_configuracao()

CLIENT_ID = os.environ.get('ADRI_MICROSOFT_CLIENT_ID', '14bc533a-a8a2-4e2b-9142-773dcd117269')
REDIRECT_URI = "http://localhost:5000/callback"

# Escopos pedidos no login Microsoft. Um lugar so: eles precisam ser
# identicos na URL de autorizacao e na troca do code por token, e antes
# estavam escritos como literal em auth.py e em app.py -- alterar um e
# esquecer o outro devolve invalid_grant sem explicacao.
#
# `offline_access` e o que rende o refresh_token. Sem ele a Microsoft entrega
# apenas um access_token de ~1 hora, e depois disso o operador tinha de
# refazer o login no navegador para conseguir exportar uma planilha.
ESCOPOS_MICROSOFT = "User.Read Files.ReadWrite offline_access"

URL_TOKEN_MICROSOFT = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
URL_AUTORIZACAO_MICROSOFT = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
# Credenciais de integracao. Vem do cofre cifrado quando ele as tem; do
# ambiente ou do .env quando nao. Ver `segredos.py` para a precedencia e para
# o limite honesto do que o DPAPI protege.
GEMINI_API_KEY = segredos.obter('GEMINI_API_KEY')

# Versao do aplicativo. Lida do package.json para nao existirem duas verdades:
# o instalador, o titulo da janela e a sonda de identidade precisam concordar,
# e um numero digitado a mao aqui envelheceria na primeira release.
def _versao_do_package_json() -> str:
    import json
    for base in (getattr(sys, '_MEIPASS', None), os.path.dirname(os.path.dirname(os.path.abspath(__file__)))):
        if not base:
            continue
        caminho = os.path.join(base, 'package.json')
        try:
            with open(caminho, 'r', encoding='utf-8') as arquivo:
                versao = json.load(arquivo).get('version')
            if versao:
                return str(versao)
        except (OSError, ValueError):
            continue
    return 'desconhecida'


VERSAO_DO_APP = _versao_do_package_json()

# Hosts tratados como loopback ao montar a lista de origens aceitas.
# 127.0.0.1 e localhost apontam para o mesmo servidor, mas o navegador os
# considera origens distintas -- os dois precisam ser aceitos.
ALIASES_LOOPBACK = ('127.0.0.1', 'localhost', '[::1]')

_oauth_pending: dict = {}

# Pagina exibida no navegador ao voltar do login Microsoft. Usa a mesma
# linguagem visual do app (fundo escuro, cartao com blur, cantos arredondados)
# em vez do tema claro generico que destoava do restante.
_CALLBACK_TEMPLATE = """\
<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<title>Adri Poltronas</title>
<style>
    /* Paleta espelhada de frontend/css/tokens.css. Esta pagina abre no
       navegador do sistema, fora do app, entao nao alcanca a folha de
       estilo -- os valores precisam estar aqui. Ao mexer na identidade
       visual, os dois arquivos andam juntos. */
    :root {
        --ok: #4E6B3C; --ok-suave: #E7EDDF; --ok-borda: #C4D3B2;
        --erro: #A63D2E; --erro-suave: #F7E4DF; --erro-borda: #E5BDB3;
        --fundo: #F2EEE7; --superficie: #FBF9F5; --borda: #E0D8C9;
        --texto: #2B2620; --texto-2: #6B6153; --texto-3: #9A8F7E;
    }
    * { box-sizing: border-box; }
    body {
        margin: 0; min-height: 100vh;
        display: flex; align-items: center; justify-content: center;
        font-family: 'Inter', 'Segoe UI', system-ui, -apple-system, sans-serif;
        background: var(--fundo);
        color: var(--texto); padding: 1.5rem;
    }
    .cartao {
        max-width: 440px; width: 100%; text-align: center;
        background: var(--superficie);
        border: 1px solid var(--borda);
        border-radius: 10px; padding: 2.5rem 2rem;
        box-shadow: 0 4px 12px rgba(74, 58, 40, 0.08), 0 12px 32px rgba(74, 58, 40, 0.09);
        animation: entrar 0.18s cubic-bezier(0, 0, 0.2, 1);
    }
    @keyframes entrar { from { opacity: 0; transform: translateY(-6px); } }
    .icone {
        width: 48px; height: 48px; margin: 0 auto 1.25rem;
        border-radius: 50%; display: flex; align-items: center; justify-content: center;
        background: var(--cor-suave); border: 1px solid var(--cor-borda); color: var(--cor);
    }
    h2 { font-size: 1.125rem; font-weight: 600; margin: 0 0 0.75rem; color: var(--cor); }
    .mensagem { color: var(--texto); line-height: 1.5; margin: 0 0 0.5rem; font-size: 0.875rem; }
    .instrucao { color: var(--texto-2); font-size: 0.8125rem; margin: 0; word-break: break-word; }
    .rodape { color: var(--texto-3); font-size: 0.75rem; margin: 1.75rem 0 0; }
    @media (prefers-reduced-motion: reduce) { .cartao { animation: none; } }
</style>
</head>
<body>
    <div class="cartao" style="
        --cor: {% if erro %}var(--erro){% else %}var(--ok){% endif %};
        --cor-suave: {% if erro %}var(--erro-suave){% else %}var(--ok-suave){% endif %};
        --cor-borda: {% if erro %}var(--erro-borda){% else %}var(--ok-borda){% endif %};">
        <div class="icone">
            {% if erro %}
            <svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
            {% else %}
            <svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
            {% endif %}
        </div>
        <h2>{{ titulo }}</h2>
        <p class="mensagem">{{ mensagem }}</p>
        <p class="instrucao">{{ instrucao }}</p>
        {% if not erro %}
        <p class="rodape">Esta aba pode ser fechada manualmente.</p>
        {% endif %}
    </div>
    <script>try { setTimeout(function(){ window.close(); }, 3000); } catch(e) {}</script>
</body>
</html>
"""
