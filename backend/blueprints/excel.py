# backend/blueprints/excel.py
"""Blueprint de exportação Excel para OneDrive."""
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
import logging
from flask import Blueprint, request, jsonify

import database
import microsoft
import planilha
from limites import LIMITE_ONEDRIVE, limiter
from permissoes import exigir_permissao

log = logging.getLogger("adri.excel")

excel_bp = Blueprint('excel', __name__, url_prefix='/api/excel')

NOME_ARQUIVO_PADRAO = "Clientes_AdriPoltronas"
TIMEOUT_ONEDRIVE_S = 30

# Caracteres proibidos em nome de arquivo no Windows e no OneDrive.
_RE_CARACTERES_PROIBIDOS = re.compile(r'[\\/:*?"<>|]')


def nome_arquivo_seguro(nome_bruto: str) -> str:
    """
    Reduz o nome informado pelo usuario a um nome de arquivo simples e .xlsx.

    `urllib.parse.quote` usa safe='/' por padrao, entao barras passavam
    intactas para a URL do Graph: um nome como '../../Documentos/relatorio'
    virava 'root:/../../Documentos/relatorio.xlsx:/content' e escrevia fora
    do lugar pretendido dentro do OneDrive do usuario.

    Aqui o nome e reduzido ao ultimo segmento de caminho, tem os caracteres
    proibidos removidos e volta ao padrao quando nao sobra nada utilizavel.
    """
    nome = (nome_bruto or '').strip().replace('\\', '/')
    # basename descarta qualquer componente de diretorio, inclusive '..'
    nome = os.path.basename(nome)
    nome = _RE_CARACTERES_PROIBIDOS.sub('', nome)
    # Pontos e espacos nas pontas viram nomes invalidos no Windows ('...')
    nome = nome.strip('. ')

    if nome.lower().endswith('.xlsx'):
        nome = nome[:-5].strip('. ')
    if not nome:
        nome = NOME_ARQUIVO_PADRAO
    return f"{nome}.xlsx"


CABECALHOS = ["Nome", "CEP", "Rua", "Bairro", "Cidade", "Entrega/Retirada", "Observacoes"]
CAMPOS = ['nome', 'cep', 'rua', 'bairro', 'cidade', 'entrega_retirada', 'observacoes']


@excel_bp.route('/enviar', methods=['POST'])
@exigir_permissao("config.integracao.microsoft")
# Cota do Microsoft Graph, e o arquivo enviado e grande.
@limiter.limit(LIMITE_ONEDRIVE)
def enviar_excel_onedrive():
    # `obter_token_valido` renova em silencio quando o access_token venceu.
    # Antes daqui a exportacao usava o token gravado tal como estava: passada
    # a hora de validade, o Graph respondia 401 e o operador perdia a
    # selecao de clientes para refazer o login.
    token = microsoft.obter_token_valido()
    if not token:
        return jsonify({"erro": "Usuario nao autenticado."}), 401
    dados_requisicao = request.get_json(silent=True) or {}
    ids_selecionados = dados_requisicao.get('ids', [])
    nome_personalizado = dados_requisicao.get('nome_arquivo', '').strip()
    if not ids_selecionados:
        return jsonify({"erro": "Nenhum cliente selecionado."}), 400
    clientes = database.listar_clientes_por_ids(ids_selecionados)
    if not clientes:
        return jsonify({"erro": "Clientes nao encontrados."}), 404
    nome_arquivo = nome_arquivo_seguro(nome_personalizado)

    corpo_binario = planilha.construir_planilha("Clientes", CABECALHOS, CAMPOS, clientes).read()

    # safe='' e obrigatorio: com o padrao (safe='/') uma barra que
    # escapasse do saneamento acima ainda alteraria o caminho no Graph.
    caminho_no_drive = urllib.parse.quote(nome_arquivo, safe='')
    url_upload = f"https://graph.microsoft.com/v1.0/me/drive/root:/{caminho_no_drive}:/content"
    req_upload = urllib.request.Request(url_upload, data=corpo_binario,  # noqa: S310 - URL montada de constante do proprio codigo, sempre https
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
        method='PUT')
    try:
        with urllib.request.urlopen(req_upload, timeout=TIMEOUT_ONEDRIVE_S) as resp:  # noqa: S310 - URL montada de constante do proprio codigo, sempre https
            retorno = json.loads(resp.read().decode('utf-8'))
            web_url = retorno.get('webUrl')
        if web_url:
            webbrowser.open(web_url)
        return jsonify({"mensagem": "Planilha enviada!", "url": web_url}), 200
    except urllib.error.HTTPError as e:
        log.error("Graph recusou o envio (HTTP %s).", e.code)
        if e.code == 401:
            database.excluir_sessao()
            return jsonify({"erro": "Sessao expirada. Reconecte."}), 401
        return jsonify({"erro": f"Erro {e.code} ao enviar para Excel."}), 502
    except urllib.error.URLError as e:
        log.error("Falha de conexão com o Graph (%s).", type(e.reason).__name__)
        return jsonify({"erro": "Falha de conexao com a Microsoft."}), 502
