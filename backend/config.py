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

_oauth_pending: dict = {}

_CALLBACK_TEMPLATE = """\
<html>
<body style="font-family:sans-serif; text-align:center; padding-top:60px; background:#f4f6f9; color:#333;">
    <div style="max-width:480px; margin:0 auto; background:white; border-radius:12px; padding:40px 32px; box-shadow:0 8px 30px rgba(0,0,0,0.08);">
        <div style="font-size:48px; margin-bottom:16px;">{% if erro %}&#10060;{% else %}&#9989;{% endif %}</div>
        <h2 style="color:{% if erro %}#e74c3c{% else %}#27ae60{% endif %}; margin:0 0 12px;">{{ titulo }}</h2>
        <p style="color:#555; line-height:1.6; margin:0 0 8px;">{{ mensagem }}</p>
        <p style="color:#888; font-size:0.9rem; margin:0;">{{ instrucao }}</p>
        {% if not erro %}
        <p style="color:#aaa; font-size:0.8rem; margin-top:24px;">Esta aba pode ser fechada manualmente.</p>
        {% endif %}
    </div>
    <script>try { setTimeout(function(){ window.close(); }, 3000); } catch(e) {}</script>
</body>
</html>
"""
