"""
Rotas da licenca de uso.

Estas rotas sao ISENTAS do bloqueio de licenca, pelo motivo evidente: sao elas
que permitem sair do bloqueio. Exigir licenca para consultar a licenca ou para
gerar a cobranca dela trancaria o operador do lado de fora com a chave dentro.

Continuam sujeitas aos outros guardas -- host de loopback, capacidade e sessao
Microsoft. Quem nao esta autenticado no app tambem nao compra a licenca dele.
"""
import logging

from flask import Blueprint, jsonify, request

import licenca
import mercadopago
from limites import limiter

log = logging.getLogger("adri.licenca.rotas")

licenca_bp = Blueprint('licenca', __name__, url_prefix='/api/licenca')

# A lista das isencoes vive em `licenca.py`, junto do guarda que a consulta.
# Uma lista, e nao o prefixo `/api/licenca/`: prefixo isenta sozinho toda rota
# que alguem acrescentar aqui depois, e nem toda rota nova precisa ser isenta.
ROTAS_ISENTAS_DE_LICENCA = licenca.ROTAS_ISENTAS


@licenca_bp.route('/status', methods=['GET'])
def status():
    """
    Situacao da licenca: dias restantes, valor, e se ha cobranca em aberto.

    Chamada na abertura do app e enquanto a tela de compra espera o pagamento.
    """
    situacao = licenca.situacao()
    situacao['mercadopago_configurado'] = mercadopago.esta_configurado()
    return jsonify(situacao), 200


@licenca_bp.route('/cobranca', methods=['POST'])
# Cada chamada cria uma cobranca REAL no Mercado Pago. A idempotencia do
# cliente HTTP cobre a repeticao acidental da mesma tentativa; este limite
# cobre o resto.
@limiter.limit("5 per minute")
def gerar_cobranca():
    """Gera o Pix da licenca e devolve o QR Code para a tela."""
    situacao = licenca.situacao()
    if situacao['estado'] == licenca.ESTADO_PAGA:
        return jsonify({"erro": "Esta instalacao ja tem licenca ativa."}), 409

    if not mercadopago.esta_configurado():
        return jsonify({
            "erro": "Pagamento indisponivel: o Mercado Pago nao esta "
                    "configurado nesta instalacao."
        }), 503

    dados = request.get_json(silent=True) or {}
    email = (dados.get('email') or '').strip()[:120]

    resposta = mercadopago.criar_cobranca_pix(
        valor_centavos=licenca.VALOR_DA_LICENCA_CENTAVOS,
        descricao="Licenca de uso - Adri Poltronas",
        referencia=situacao['referencia'],
        email_do_pagador=email,
    )
    if resposta.get('_erro'):
        log.error("[LICENCA] Falha ao gerar cobranca no Mercado Pago.")
        return jsonify({"erro": "Nao foi possivel gerar a cobranca agora."}), 502

    # Guardado ANTES de devolver: se o app for fechado com o Pix na tela, a
    # verificacao automatica da proxima abertura precisa saber a quem
    # perguntar.
    licenca.guardar_pagamento_pendente(resposta['pagamento_id'])
    return jsonify(resposta), 201


@licenca_bp.route('/verificar', methods=['POST'])
@limiter.limit("20 per minute")
def verificar():
    """
    Pergunta ao Mercado Pago se a cobranca em aberto foi paga.

    E o que substitui o webhook: o Flask escuta em loopback e um servidor na
    internet nao alcanca este endereco. Quem pergunta e o app, sempre -- nunca
    o contrario.

    A licenca so e liberada pelo que o Mercado Pago RESPONDE. O cliente nao
    tem como afirmar que pagou.
    """
    situacao = licenca.situacao()
    if situacao['estado'] == licenca.ESTADO_PAGA:
        return jsonify(situacao), 200

    pagamento_id = situacao.get('pagamento_id') or ''
    if not pagamento_id:
        return jsonify({**situacao, "verificado": False,
                        "motivo": "sem_cobranca"}), 200

    resposta = mercadopago.obter_pagamento(pagamento_id)
    if resposta.get('_erro'):
        # Erro de rede nao e informacao sobre o pagamento. A situacao fica
        # como esta e a proxima rodada tenta de novo.
        return jsonify({**situacao, "verificado": False,
                        "motivo": "consulta_falhou"}), 200

    if resposta['pago']:
        return jsonify({**licenca.registrar_pagamento(pagamento_id),
                        "verificado": True}), 200

    return jsonify({**situacao, "verificado": True,
                    "status_do_pagamento": resposta['status'],
                    "encerrado": resposta['encerrado']}), 200
