# backend/blueprints/ia.py
"""Blueprint de IA (sugestão de bairro por CEP)."""
import re
import json
import urllib.request
import logging
from flask import Blueprint, request, jsonify

import config
from limites import LIMITE_IA, limiter

log = logging.getLogger("adri.ia")

ia_bp = Blueprint('ia', __name__, url_prefix='/api/ia')


@ia_bp.route('/sugestao-bairro', methods=['POST'])
# Cota do Gemini: a sugestao e disparada por digitacao no formulario.
@limiter.limit(LIMITE_IA)
def ia_sugestao_bairro():
    dados = request.get_json(silent=True) or {}
    cep = (dados.get('cep') or '').replace('-', '').strip()
    if len(cep) != 8 or not cep.isdigit():
        return jsonify({"erro": "CEP invalido."}), 400
    try:
        url_viacep = f"https://viacep.com.br/ws/{cep}/json/"
        with urllib.request.urlopen(urllib.request.Request(url_viacep), timeout=5) as resp:
            dados_cep = json.loads(resp.read().decode('utf-8'))
            if not dados_cep.get('erro'):
                return jsonify({"bairro": dados_cep.get('bairro', ''), "cidade": dados_cep.get('localidade', ''),
                    "rua": dados_cep.get('logradouro', ''), "uf": dados_cep.get('uf', ''), "fonte": "ViaCEP"})
    except Exception as e:
        log.warning("ViaCEP falhou: %s", e)
    if not config.GEMINI_API_KEY:
        return jsonify({"erro": "Nao foi possivel buscar dados para este CEP."}), 502
    try:
        prompt = f"Para o CEP brasileiro {cep[:5]}-{cep[5:]}, quais sao os bairros mais provaveis? Responda APENAS com JSON: {{\"bairro\": \"nome do bairro\"}}"
        payload = json.dumps({"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"temperature": 0.3, "maxOutputTokens": 200}}).encode()
        req = urllib.request.Request(f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={config.GEMINI_API_KEY}",
            data=payload, headers={"Content-Type": "application/json"}, method='POST')
        with urllib.request.urlopen(req, timeout=10) as resp:
            resultado = json.loads(resp.read().decode('utf-8'))
            texto = resultado.get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', '')
            match = re.search(r'\{[^}]+\}', texto)
            if match:
                return jsonify({"bairro": json.loads(match.group()).get('bairro', ''), "fonte": "Gemini AI"})
    except Exception as e:
        log.warning("Gemini falhou: %s", e)
    return jsonify({"erro": "Nao foi possivel buscar dados para este CEP."}), 502