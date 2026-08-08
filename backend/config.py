# backend/config.py
"""Configurações compartilhadas entre blueprints e app."""
import os
import logging
from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger("adri.config")

CLIENT_ID = os.environ.get('ADRI_MICROSOFT_CLIENT_ID', '14bc533a-a8a2-4e2b-9142-773dcd117269')
REDIRECT_URI = "http://localhost:5000/callback"
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')
ASAAS_API_KEY = os.environ.get('ASAAS_API_KEY', '')
ASAAS_SANDBOX = os.environ.get('ASAAS_SANDBOX', 'true').strip().lower() == 'true'
# Token que o Asaas envia no header `asaas-access-token` dos webhooks.
# Deve ser diferente da ASAAS_API_KEY (recomendacao explicita do Asaas).
ASAAS_WEBHOOK_TOKEN = os.environ.get('ASAAS_WEBHOOK_TOKEN', '')

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
    :root { --ok: #10b981; --erro: #ef4444; }
    * { box-sizing: border-box; }
    body {
        margin: 0; min-height: 100vh;
        display: flex; align-items: center; justify-content: center;
        font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
        background: linear-gradient(-45deg, #080d1a, #0f172a, #04060d);
        color: #f8fafc; padding: 1.5rem;
    }
    .cartao {
        max-width: 460px; width: 100%; text-align: center;
        background: rgba(30, 41, 59, 0.7);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 20px; padding: 2.5rem 2rem;
        box-shadow: 0 20px 45px rgba(0, 0, 0, 0.45);
        animation: entrar 0.35s cubic-bezier(0.34, 1.56, 0.64, 1);
    }
    @keyframes entrar { from { opacity: 0; transform: scale(0.9) translateY(16px); } }
    .icone {
        width: 64px; height: 64px; margin: 0 auto 1.25rem;
        border-radius: 50%; display: flex; align-items: center; justify-content: center;
        background: var(--cor-suave); border: 2px solid var(--cor-borda); color: var(--cor);
    }
    h2 { font-size: 1.25rem; font-weight: 700; margin: 0 0 0.75rem; color: var(--cor); }
    .mensagem { color: #cbd5e1; line-height: 1.6; margin: 0 0 0.5rem; font-size: 0.95rem; }
    .instrucao { color: #94a3b8; font-size: 0.875rem; margin: 0; word-break: break-word; }
    .rodape { color: #64748b; font-size: 0.8rem; margin: 1.75rem 0 0; }
    @media (prefers-reduced-motion: reduce) { .cartao { animation: none; } }
</style>
</head>
<body>
    <div class="cartao" style="
        --cor: {% if erro %}var(--erro){% else %}var(--ok){% endif %};
        --cor-suave: rgba({% if erro %}239, 68, 68{% else %}16, 185, 129{% endif %}, 0.15);
        --cor-borda: rgba({% if erro %}239, 68, 68{% else %}16, 185, 129{% endif %}, 0.3);">
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
