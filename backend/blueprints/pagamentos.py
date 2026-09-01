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
    cliente_id_bruto = (request.args.get('cliente_id') or '').strip()
    cliente_id = None
    if cliente_id_bruto:
        cliente_id = validators.inteiro_positivo(cliente_id_bruto)
        if cliente_id is None:
            return jsonify({"erro": "cliente_id invalido."}), 400
    status = request.args.get('status')
    pagamentos = database.listar_pagamentos(cliente_id=cliente_id, status=status)
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
    if not database.obter_cliente_por_id(pagamento['cliente_id']):
        return jsonify({"erro": "Cliente nao encontrado."}), 404
    pagamento_id = database.salvar_pagamento(
        pagamento['cliente_id'], pagamento['cliente_nome'], pagamento['valor'],
        pagamento['descricao'], pagamento['data_vencimento'], pagamento['tipo_pagamento'],
        status=pagamento['status'], data_pagamento=pagamento['data_pagamento'],
    )
    return jsonify({"mensagem": "Pagamento registrado!", "id": pagamento_id}), 201


@pagamentos_bp.route('/<int:pagamento_id>', methods=['PUT'])
def atualizar_pagamento(pagamento_id):
    dados = request.get_json(silent=True) or {}
    existente = database.obter_pagamento_por_id(pagamento_id)
    if not existente:
        return jsonify({"erro": "Pagamento nao encontrado."}), 404

    # Campos de estado ausentes no corpo sao herdados do registro atual.
    # Sem isso o validador injetava 'Pendente' por padrao, e um PUT que so
    # mudava a descricao revertia uma cobranca ja recebida -- apagando a
    # receita do faturamento sem nenhum sinal para o usuario.
    dados.setdefault('status', existente['status'])
    dados.setdefault('data_pagamento', existente.get('data_pagamento', ''))

    pagamento, erros = validators.validar_pagamento(dados)
    if erros:
        return jsonify({"erro": "Dados invalidos.", "detalhes": erros}), 400
    linhas = database.atualizar_pagamento(pagamento_id, **pagamento)
    return jsonify({"mensagem": "Pagamento atualizado!", "linhas": linhas}), 200


@pagamentos_bp.route('/<int:pagamento_id>', methods=['DELETE'])
def excluir_pagamento(pagamento_id):
    existente = database.obter_pagamento_por_id(pagamento_id)
    if not existente:
        return jsonify({"erro": "Pagamento nao encontrado."}), 404
    # A checagem vem ANTES da chamada ao Asaas. `excluir_pagamento()` so apaga
    # cobrancas pendentes, entao cancelar remoto primeiro deixava a cobranca
    # cancelada no gateway e viva no banco local -- divergencia permanente,
    # sem nenhum caminho de volta pela interface.
    if existente['status'] != 'Pendente':
        return jsonify({"erro": "So e possivel cancelar pagamentos pendentes."}), 400

    if existente.get('asaas_payment_id') and asaas.esta_configurado():
        resultado = asaas.cancelar_pagamento(existente['asaas_payment_id'])
        if resultado.get('_erro'):
            # Apagar localmente aqui seria pior que falhar: a cobranca segue
            # viva no Asaas, o cliente ainda pode paga-la, e o registro que
            # permitiria conciliar teria sumido.
            log.warning("Falha ao cancelar no Asaas: %s", resultado)
            return jsonify({"erro": "Falha ao cancelar a cobranca no Asaas. Tente novamente."}), 502

    linhas = database.excluir_pagamento(pagamento_id)
    if linhas == 0:
        return jsonify({"erro": "Nao foi possivel cancelar a cobranca. Tente novamente."}), 400
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
    pagamento_id = validators.inteiro_positivo(dados.get('pagamento_id'))
    if pagamento_id is None:
        return jsonify({"erro": "pagamento_id e obrigatorio e deve ser um numero positivo."}), 400
    pagamento = database.obter_pagamento_por_id(pagamento_id)
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