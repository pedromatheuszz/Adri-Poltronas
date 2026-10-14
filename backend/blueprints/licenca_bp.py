"""
Rotas da licenca de uso.

Estas rotas sao ISENTAS do bloqueio de licenca, pelo motivo evidente: sao elas
que permitem sair do bloqueio. Exigir licenca para consultar a licenca ou para
gerar a cobranca dela trancaria o operador do lado de fora com a chave dentro.

Continuam sujeitas aos outros guardas -- host de loopback, capacidade e login
local. O desenvolvedor autenticado pode usar as rotas de controle.
"""
import logging

from flask import Blueprint, g, jsonify, request

import licenca
import licenca_remota
import mercadopago
from limites import limiter
from permissoes import exigir_permissao, desenvolvedor_necessario

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
    if getattr(g, 'erp_usuario_role', '') == 'desenvolvedor':
        situacao = {
            "estado": licenca.ESTADO_DESATIVADA,
            "dias_restantes": None,
            "teste_modo": "desativado",
        }
    elif licenca.situacao()['estado'] == licenca.ESTADO_PAGA:
        situacao = licenca.situacao()
    else:
        user_id = getattr(g, 'erp_usuario_id', None)
        remota = licenca_remota.sincronizar_usuario(user_id) if user_id else None
        if remota:
            situacao = remota
        else:
            cache = licenca_remota.situacao_em_cache(user_id) if user_id else None
            situacao = cache or (licenca.situacao_usuario(user_id) if user_id else licenca.situacao())
    situacao['mercadopago_configurado'] = mercadopago.esta_configurado()
    return jsonify(situacao), 200


@licenca_bp.route('/cobranca', methods=['POST'])
@exigir_permissao("config.licenca.gerenciar")
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
@exigir_permissao("config.licenca.gerenciar")
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


@licenca_bp.route('/teste', methods=['POST'])
@desenvolvedor_necessario
@limiter.limit("5 per minute")
def controlar_teste():
    """Libera 30 dias de teste ou desativa o vencimento, apenas para dev."""
    dados = request.get_json(silent=True) or {}
    acao = (dados.get('acao') or '').strip()
    if acao == 'liberar_30_dias':
        return jsonify(licenca.liberar_teste_30_dias()), 200
    if acao == 'desativar':
        return jsonify(licenca.desativar_teste()), 200
    return jsonify({"erro": "Ação inválida."}), 400


@licenca_bp.route('/remota/contas', methods=['GET'])
@desenvolvedor_necessario
@limiter.limit("30 per minute")
def listar_contas_remotas():
    """Lista contas conhecidas pela API central, apenas para o desenvolvedor."""
    if not licenca_remota.api_configurada():
        return jsonify({"erro": "Configure ADRI_LICENCA_API_URL no computador do desenvolvedor.",
                        "configurada": False}), 503
    try:
        return jsonify({**licenca_remota.listar_contas_admin(), "configurada": True}), 200
    except RuntimeError as erro:
        log.warning("[LICENCA] Erro na consulta da API central: %s", erro)
        return jsonify({"erro": str(erro), "configurada": True}), 503
    except Exception:
        log.warning("[LICENCA] Não foi possível consultar a API central.")
        return jsonify({"erro": "API central indisponível ou token administrativo não configurado.",
                        "configurada": True}), 503


@licenca_bp.route('/remota/contas/<license_id>', methods=['POST'])
@desenvolvedor_necessario
@limiter.limit("30 per minute")
def controlar_conta_remota(license_id):
    """Aplica pagamento, extensão de teste ou suspensão no servidor central."""
    dados = request.get_json(silent=True) or {}
    acao = dados.get('acao')
    try:
        resposta = licenca_remota.controlar_conta_admin(license_id, acao)
    except (ValueError, RuntimeError) as erro:
        return jsonify({"erro": str(erro)}), 400
    except Exception:
        log.warning("[LICENCA] Não foi possível alterar licença central.")
        return jsonify({"erro": "API central indisponível ou token administrativo não configurado."}), 503
    return jsonify(resposta), 200
