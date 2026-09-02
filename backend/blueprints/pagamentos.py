# backend/blueprints/pagamentos.py
"""Blueprint de pagamentos (CRUD, Asaas, webhook)."""
import time
import logging
from flask import Blueprint, request, jsonify

import database
import validators
import asaas
from erp.financeiro import emissao, reconciliacao

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
    """
    Marca uma cobranca como recebida.

    Quando ha cobranca no Asaas, confere com o gateway antes. Sem essa
    checagem, um clique marcava 'Recebido' com a cobranca ainda aberta la, e o
    ERP passava a declarar uma receita que ninguem tinha recebido -- o pior
    tipo de erro num modulo financeiro, porque o numero errado parece certo.

    O operador pode forcar (`{"forcar": true}`) para o caso legitimo de
    pagamento feito por fora do gateway. Forcar exige motivo, e o motivo vai
    para a trilha de auditoria: e a diferenca entre uma excecao registrada e
    um numero que ninguem sabe explicar.
    """
    existente = database.obter_pagamento_por_id(pagamento_id)
    if not existente:
        return jsonify({"erro": "Pagamento nao encontrado."}), 404
    if existente.get('status') == 'Recebido':
        return jsonify({"mensagem": "Pagamento ja estava confirmado."}), 200

    corpo = request.get_json(silent=True) or {}
    forcar = bool(corpo.get('forcar'))
    motivo = (corpo.get('motivo') or '').strip()

    if forcar:
        if not motivo:
            return jsonify({
                "erro": "Para confirmar sem conferir com o Asaas, informe o motivo.",
            }), 400
    elif asaas.esta_configurado():
        pode, detalhe = reconciliacao.confirmar_com_o_gateway(
            database.conectar, asaas, existente
        )
        if not pode:
            return jsonify({"erro": detalhe, "pode_forcar": True}), 409

    database.atualizar_pagamento(pagamento_id, status='Recebido',
        data_pagamento=time.strftime('%Y-%m-%d'))
    if forcar:
        log.warning(
            "[PAGAMENTO] Confirmacao manual forcada em %s. Motivo: %s",
            pagamento_id, motivo,
        )
        database.registrar_observacao_de_pagamento(
            pagamento_id, f"Confirmacao manual sem conferencia no gateway: {motivo}"
        )
    return jsonify({"mensagem": "Pagamento confirmado!"}), 200


@pagamentos_bp.route('/reconciliar', methods=['POST'])
def reconciliar_pagamentos():
    """
    Pergunta ao Asaas o estado atual das cobrancas em aberto.

    E o que substitui o webhook numa instalacao normal: o Flask escuta em
    loopback, entao um servidor na internet nunca alcanca este endereco. Uma
    consulta de saida atravessa qualquer firewall e nao expoe nada.
    """
    if not asaas.esta_configurado():
        return jsonify({"erro": "Integracao Asaas nao configurada."}), 503
    resumo = reconciliacao.reconciliar(database.conectar, asaas)
    return jsonify(resumo), 200


def _dados_da_cobranca_existente(pagamento: dict) -> dict:
    """Resposta para uma cobranca que ja existe -- nao cria nada."""
    tipo = pagamento.get('tipo_pagamento', 'Pix')
    resposta = {
        "mensagem": f"Cobranca {tipo} ja emitida para este pagamento.",
        "asaas_payment_id": pagamento.get('asaas_payment_id', ''),
        "tipo": tipo,
        "ja_existia": True,
    }
    if tipo == 'Pix':
        resposta['pix_payload'] = pagamento.get('pix_payload', '')
        resposta['pix_qr_code'] = pagamento.get('pix_qr_code', '')
    elif tipo == 'Boleto':
        resposta['boleto_url'] = pagamento.get('boleto_url', '')
        resposta['nosso_numero'] = pagamento.get('nosso_numero', '')
    return resposta


@pagamentos_bp.route('/gerar-cobranca', methods=['POST'])
def gerar_cobranca():
    """
    Gera cobranca Pix ou Boleto no Asaas.

    Idempotente: a mesma chamada repetida devolve a MESMA cobranca em vez de
    criar outra. Ver `erp/financeiro/emissao.py` para o porque -- em resumo,
    criar cobranca e uma chamada de rede, e sem registrar a intencao antes de
    sair para a rede nao ha como distinguir "nao criou" de "criou e a resposta
    se perdeu". O cliente recebia duas cobrancas do mesmo valor.
    """
    if not asaas.esta_configurado():
        return jsonify({"erro": "Integracao Asaas nao configurada. Defina ASAAS_API_KEY."}), 503

    dados = request.get_json(silent=True) or {}
    pagamento_id = validators.inteiro_positivo(dados.get('pagamento_id'))
    if pagamento_id is None:
        return jsonify({"erro": "pagamento_id e obrigatorio e deve ser um numero positivo."}), 400

    pagamento = database.obter_pagamento_por_id(pagamento_id)
    if not pagamento:
        return jsonify({"erro": "Pagamento nao encontrado."}), 404

    # 1. Ja emitida. Nao se cria outra: devolve-se a que existe.
    if pagamento.get('asaas_payment_id'):
        return jsonify(_dados_da_cobranca_existente(pagamento)), 200

    # 2. Ha uma tentativa anterior em aberto. Pergunta ao Asaas antes de
    #    emitir -- e o passo que evita a segunda cobranca.
    estado_anterior = (pagamento.get('asaas_emissao_estado') or '').strip()
    if estado_anterior in (emissao.ESTADO_INICIADA, emissao.ESTADO_FALHOU):
        try:
            recuperada = emissao.reconciliar_emissao_em_aberto(
                database.conectar, pagamento, asaas
            )
        except emissao.EmissaoJaEmCurso as erro:
            return jsonify({"erro": str(erro)}), 409
        if recuperada:
            atual = database.obter_pagamento_por_id(pagamento_id) or pagamento
            return jsonify(_dados_da_cobranca_existente(atual)), 200

    # 3. Reivindica a emissao. O UPDATE condicional la dentro e o que resolve
    #    clique duplo e requisicoes simultaneas.
    try:
        referencia, pagamento = emissao.reivindicar(database.conectar, pagamento_id)
    except emissao.EmissaoNaoPermitida as erro:
        return jsonify({"erro": str(erro)}), 409
    except emissao.EmissaoJaEmCurso as erro:
        return jsonify({"erro": str(erro)}), 409

    cliente = database.obter_cliente_por_id(pagamento['cliente_id'])
    if not cliente:
        emissao.falhar(database.conectar, pagamento_id, "cliente inexistente")
        return jsonify({"erro": "Cliente nao encontrado."}), 404

    asaas_customer_id = database.obter_ou_criar_cliente_asaas(
        pagamento['cliente_id'], cliente['nome'],
        cidade=cliente.get('cidade'), bairro=cliente.get('bairro'),
        rua=cliente.get('rua'), cep=cliente.get('cep'),
    )
    if not asaas_customer_id:
        emissao.falhar(database.conectar, pagamento_id, "falha ao criar cliente no Asaas")
        return jsonify({"erro": "Falha ao criar cliente no Asaas."}), 502

    tipo = pagamento.get('tipo_pagamento', 'Pix')
    if tipo == 'Pix':
        resultado = asaas.criar_cobranca_pix(
            asaas_customer_id, pagamento['valor'], pagamento['data_vencimento'],
            pagamento.get('descricao', ''), referencia_externa=referencia,
        )
    elif tipo == 'Boleto':
        resultado = asaas.criar_cobranca_boleto(
            asaas_customer_id, pagamento['valor'], pagamento['data_vencimento'],
            pagamento.get('descricao', ''), referencia_externa=referencia,
        )
    else:
        emissao.falhar(database.conectar, pagamento_id, f"tipo invalido: {tipo}")
        return jsonify({"erro": "Tipo de pagamento invalido."}), 400

    if resultado.get('_erro'):
        # A referencia fica gravada: se a falha foi de rede, a cobranca pode
        # ter sido criada assim mesmo, e a proxima tentativa vai perguntar.
        emissao.falhar(database.conectar, pagamento_id, str(resultado.get('_erro')))
        return jsonify({"erro": "Falha ao gerar cobranca no Asaas.", "detalhes": resultado}), 502

    asaas_payment_id = resultado.get('id', '')
    campos_extras = {}
    if tipo == 'Boleto':
        campos_extras['boleto_url'] = resultado.get('bankSlipUrl', '')
        campos_extras['nosso_numero'] = resultado.get('nossoNumero', '')
    emissao.concluir(database.conectar, pagamento_id, asaas_payment_id, **campos_extras)

    resposta = {
        "mensagem": f"Cobranca {tipo} gerada com sucesso!",
        "asaas_payment_id": asaas_payment_id,
        "tipo": tipo,
        "ja_existia": False,
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