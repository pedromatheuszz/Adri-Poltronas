# backend/blueprints/pagamentos.py
"""Blueprint de pagamentos (CRUD, Asaas, webhook)."""
import time
import logging
from flask import Blueprint, request, jsonify

import database
import validators
import asaas

log = logging.getLogger("adri.pagamentos")

pagamentos_bp = Blueprint('pagamentos', __name__, url_prefix='/api/pagamentos')


@pagamentos_bp.route('', methods=['GET'])
def listar_pagamentos():
    cliente_id = request.args.get('cliente_id')
    status = request.args.get('status')
    pagamentos = database.listar_pagamentos(
        cliente_id=int(cliente_id) if cliente_id else None, status=status
    )
    return jsonify(pagamentos)


@pagamentos_bp.route('/metricas')
def pagamentos_metricas():
    return jsonify(database.obter_metricas_pagamentos())


@pagamentos_bp.route('/asaas-status')
def asaas_status():
    return jsonify({
        "configurado": asaas.esta_configurado(),
        "ambiente": asaas.ambiente(),
    })


@pagamentos_bp.route('', methods=['POST'])
def criar_pagamento():
    pagamento, erros = validators.validar_pagamento(request.get_json(silent=True) or {})
    if erros:
        return jsonify({"erro": "Dados invalidos.", "detalhes": erros}), 400
    pagamento_id = database.salvar_pagamento(
        pagamento['cliente_id'], pagamento['cliente_nome'], pagamento['valor'],
        pagamento['descricao'], pagamento['data_vencimento'], pagamento['tipo_pagamento'],
    )
    return jsonify({"mensagem": "Pagamento registrado!", "id": pagamento_id}), 201


@pagamentos_bp.route('/<int:pagamento_id>', methods=['PUT'])
def atualizar_pagamento(pagamento_id):
    dados = request.get_json(silent=True) or {}
    pagamento, erros = validators.validar_pagamento(dados)
    if erros:
        return jsonify({"erro": "Dados invalidos.", "detalhes": erros}), 400
    existente = database.obter_pagamento_por_id(pagamento_id)
    if not existente:
        return jsonify({"erro": "Pagamento nao encontrado."}), 404
    linhas = database.atualizar_pagamento(pagamento_id, **pagamento)
    return jsonify({"mensagem": "Atualizado!", "linhas": linhas}), 200


@pagamentos_bp.route('/<int:pagamento_id>', methods=['DELETE'])
def excluir_pagamento(pagamento_id):
    existente = database.obter_pagamento_por_id(pagamento_id)
    if not existente:
        return jsonify({"erro": "Pagamento nao encontrado."}), 404
    if existente.get('asaas_payment_id') and asaas.esta_configurado():
        resultado = asaas.cancelar_pagamento(existente['asaas_payment_id'])
        if resultado.get('_erro'):
            log.warning("Falha ao cancelar no Asaas: %s", resultado)
    linhas = database.excluir_pagamento(pagamento_id)
    if linhas == 0:
        return jsonify({"erro": "Nao foi possivel excluir (so e possivel cancelar pagamentos pendentes)."}), 400
    return jsonify({"mensagem": "Pagamento cancelado!"}), 200


@pagamentos_bp.route('/<int:pagamento_id>/confirmar', methods=['POST'])
def confirmar_pagamento(pagamento_id):
    existente = database.obter_pagamento_por_id(pagamento_id)
    if not existente:
        return jsonify({"erro": "Pagamento nao encontrado."}), 404
    database.atualizar_pagamento(pagamento_id, status='Recebido',
        data_pagamento=time.strftime('%Y-%m-%d'))
    return jsonify({"mensagem": "Pagamento confirmado!"}), 200


@pagamentos_bp.route('/gerar-cobranca', methods=['POST'])
def gerar_cobranca():
    """Gera cobranca Pix ou Boleto no Asaas e retorna os dados."""
    if not asaas.esta_configurado():
        return jsonify({"erro": "Integracao Asaas nao configurada. Defina ASAAS_API_KEY."}), 503
    dados = request.get_json(silent=True) or {}
    pagamento_id = dados.get('pagamento_id')
    if not pagamento_id:
        return jsonify({"erro": "pagamento_id e obrigatorio."}), 400
    pagamento = database.obter_pagamento_por_id(int(pagamento_id))
    if not pagamento:
        return jsonify({"erro": "Pagamento nao encontrado."}), 404
    cliente = database.obter_cliente_por_id(pagamento['cliente_id'])
    if not cliente:
        return jsonify({"erro": "Cliente nao encontrado."}), 404
    asaas_customer_id = database.obter_ou_criar_cliente_asaas(
        pagamento['cliente_id'], cliente['nome'],
        cidade=cliente.get('cidade'), bairro=cliente.get('bairro'),
        rua=cliente.get('rua'), cep=cliente.get('cep'),
    )
    if not asaas_customer_id:
        return jsonify({"erro": "Falha ao criar cliente no Asaas."}), 502
    tipo = pagamento.get('tipo_pagamento', 'Pix')
    if tipo == 'Pix':
        resultado = asaas.criar_cobranca_pix(
            asaas_customer_id, pagamento['valor'], pagamento['data_vencimento'],
            pagamento.get('descricao', ''),
        )
    elif tipo == 'Boleto':
        resultado = asaas.criar_cobranca_boleto(
            asaas_customer_id, pagamento['valor'], pagamento['data_vencimento'],
            pagamento.get('descricao', ''),
        )
    else:
        return jsonify({"erro": "Tipo de pagamento invalido."}), 400
    if resultado.get('_erro'):
        return jsonify({"erro": "Falha ao gerar cobranca no Asaas.", "detalhes": resultado}), 502
    asaas_payment_id = resultado.get('id', '')
    update_fields = {'asaas_payment_id': asaas_payment_id}
    if tipo == 'Boleto':
        update_fields['boleto_url'] = resultado.get('bankSlipUrl', '')
        update_fields['nosso_numero'] = resultado.get('nossoNumero', '')
    database.atualizar_pagamento(pagamento_id, **update_fields)
    resposta = {
        "mensagem": f"Cobranca {tipo} gerada com sucesso!",
        "asaas_payment_id": asaas_payment_id,
        "tipo": tipo,
    }
    if tipo == 'Pix':
        pix_data = asaas.obter_qr_code_pix(asaas_payment_id)
        if not pix_data.get('_erro'):
            database.atualizar_pagamento(pagamento_id,
                pix_payload=pix_data.get('payload', ''),
                pix_qr_code=pix_data.get('encodedImage', ''),
            )
            resposta['pix_payload'] = pix_data.get('payload', '')
            resposta['pix_qr_code'] = pix_data.get('encodedImage', '')
        else:
            log.warning("Falha ao obter QR Code Pix: %s", pix_data)
    elif tipo == 'Boleto':
        resposta['boleto_url'] = resultado.get('bankSlipUrl', '')
        resposta['nosso_numero'] = resultado.get('nossoNumero', '')
    return jsonify(resposta), 201


@pagamentos_bp.route('/<int:pagamento_id>/cobranca-dados')
def obter_dados_cobranca(pagamento_id):
    """Retorna dados da cobranca (QR Code Pix ou URL Boleto)."""
    pagamento = database.obter_pagamento_por_id(pagamento_id)
    if not pagamento:
        return jsonify({"erro": "Pagamento nao encontrado."}), 404
    resposta = {
        "id": pagamento['id'],
        "tipo_pagamento": pagamento.get('tipo_pagamento', 'Pix'),
        "valor": pagamento['valor'],
        "status": pagamento['status'],
        "asaas_payment_id": pagamento.get('asaas_payment_id', ''),
    }
    if pagamento.get('tipo_pagamento') == 'Pix':
        resposta['pix_payload'] = pagamento.get('pix_payload', '')
        resposta['pix_qr_code'] = pagamento.get('pix_qr_code', '')
    elif pagamento.get('tipo_pagamento') == 'Boleto':
        resposta['boleto_url'] = pagamento.get('boleto_url', '')
        resposta['nosso_numero'] = pagamento.get('nosso_numero', '')
    return jsonify(resposta)