# backend/blueprints/excel.py
"""Blueprint de exportação Excel para OneDrive."""
import json
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
import logging
from flask import Blueprint, request, jsonify

import database
import planilha

log = logging.getLogger("adri.excel")

excel_bp = Blueprint('excel', __name__, url_prefix='/api/excel')

CABECALHOS = ["Nome", "CEP", "Rua", "Bairro", "Cidade", "Entrega/Retirada", "Observações"]
CAMPOS = ['nome', 'cep', 'rua', 'bairro', 'cidade', 'entrega_retirada', 'observacoes']


@excel_bp.route('/enviar', methods=['POST'])
def enviar_excel_onedrive():
    sessao = database.obter_sessao()
    if not sessao:
        return jsonify({"erro": "Usuario nao autenticado."}), 401
    token = sessao["token"]
    dados_requisicao = request.get_json(silent=True) or {}
    ids_selecionados = dados_requisicao.get('ids', [])
    nome_personalizado = dados_requisicao.get('nome_arquivo', '').strip()
    if not ids_selecionados:
        return jsonify({"erro": "Nenhum cliente selecionado."}), 400
    todos_clientes = database.listar_clientes()
    clientes = [c for c in todos_clientes if c['id'] in ids_selecionados]
    if not clientes:
        return jsonify({"erro": "Clientes nao encontrados."}), 404
    if not nome_personalizado:
        nome_personalizado = "Clientes_AdriPoltronas"
    nome_base = nome_personalizado.rsplit('.', 1)[0] if '.' in nome_personalizado else nome_personalizado
    nome_arquivo = f"{nome_base}.xlsx"

    corpo_binario = planilha.construir_planilha("Clientes", CABECALHOS, CAMPOS, clientes).read()

    url_upload = f"https://graph.microsoft.com/v1.0/me/drive/root:/{urllib.parse.quote(nome_arquivo)}:/content"
    req_upload = urllib.request.Request(url_upload, data=corpo_binario,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
        method='PUT')
    try:
        with urllib.request.urlopen(req_upload) as resp:
            retorno = json.loads(resp.read().decode('utf-8'))
            web_url = retorno.get('webUrl')
        if web_url:
            webbrowser.open(web_url)
        return jsonify({"mensagem": "Planilha enviada!", "url": web_url}), 200
    except urllib.error.HTTPError as e:
        erro_corpo = e.read().decode('utf-8', errors='replace')
        log.error("Graph HTTP %s: %s", e.code, erro_corpo)
        if e.code == 401:
            database.excluir_sessao()
            return jsonify({"erro": "Sessao expirada. Reconecte."}), 401
        return jsonify({"erro": f"Erro {e.code} ao enviar para Excel."}), 500
    except urllib.error.URLError as e:
        log.error("Conexao com Graph: %s", e.reason)
        return jsonify({"erro": "Falha de conexao com a Microsoft."}), 502