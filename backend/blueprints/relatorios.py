# backend/blueprints/relatorios.py
"""
Blueprint dos relatorios: a leitura reunida do que vive espalhado.

O primeiro e o financeiro. Ate aqui as parcelas a receber so eram visiveis
abrindo pedido por pedido -- o faturamento de um mes inteiro exigia N telas
e uma calculadora. O relatorio e a mesma leitura do banco, numa tabela so,
com o resumo calculado sobre as MESMAS linhas filtradas (ver
`erp/comercial/relatorios.py` para o porque isso importa).

As regras vivem no modulo de dominio; aqui e so o adaptador HTTP: query
string, permissao, formato de saida. Erro de filtro e 400 com a chave
`erro`, como manda o API_STANDARD.
"""
import logging
import time

from flask import Blueprint, jsonify, request, send_file

import database
from erp.comercial import relatorios
from erp.core import dinheiro
from permissoes import exigir_permissao
from planilha import construir_planilha

log = logging.getLogger("adri.relatorios")

relatorios_bp = Blueprint("relatorios", __name__, url_prefix="/api/relatorios")


def _filtros_da_requisicao() -> dict:
    return {
        "de": (request.args.get("de") or "").strip(),
        "ate": (request.args.get("ate") or "").strip(),
        "situacao": (request.args.get("situacao") or "").strip(),
    }


def _parcelas_da_requisicao(filtros: dict) -> list[dict]:
    with database.conectar() as conexao:
        return relatorios.parcelas(
            conexao, de=filtros["de"], ate=filtros["ate"],
            situacao=filtros["situacao"],
        )


def _para_api(parcela: dict) -> dict:
    saida = dict(parcela)
    saida["valor"] = dinheiro.serializar(int(parcela.get("valor_centavos") or 0))
    return saida


@relatorios_bp.route("/financeiro", methods=["GET"])
@exigir_permissao("financeiro.relatorios")
def relatorio_financeiro():
    filtros = _filtros_da_requisicao()
    try:
        linhas = _parcelas_da_requisicao(filtros)
    except relatorios.FiltroInvalido as erro:
        return jsonify({"erro": str(erro)}), 400

    return jsonify({
        "filtros": filtros,
        "resumo": relatorios.resumir(linhas),
        "parcelas": [_para_api(p) for p in linhas],
    })


@relatorios_bp.route("/financeiro/exportar", methods=["GET"])
@exigir_permissao("financeiro.relatorios")
def exportar_relatorio_financeiro():
    """
    A mesma tabela do relatorio, em XLSX para o contador abrir.

    E um download direto, e nao a exportacao pela Microsoft: aquela existe
    para gravar no OneDrive, esta para entregar o arquivo na mao. Dinheiro
    sai como texto formatado em reais -- numero de moeda numa celula e o
    caminho classico de centavo sumir em somas.
    """
    filtros = _filtros_da_requisicao()
    try:
        linhas = _parcelas_da_requisicao(filtros)
    except relatorios.FiltroInvalido as erro:
        return jsonify({"erro": str(erro)}), 400

    buffer = construir_planilha(
        "Parcelas",
        ["Vencimento", "Cliente", "Pedido", "Parcela", "Valor",
         "Situacao", "Pago em", "Forma"],
        ["vencimento", "cliente", "pedido", "parcela", "valor",
         "situacao", "pago_em", "forma"],
        relatorios.para_planilha(linhas),
    )
    log.info("[RELATORIOS] Exportacao XLSX: %s parcelas.", len(linhas))
    return send_file(
        buffer, mimetype="application/vnd.openxmlformats-officedocument"
                        ".spreadsheetml.sheet",
        as_attachment=True,
        download_name=f"relatorio_parcelas_{time.strftime('%Y%m%d_%H%M%S')}.xlsx",
    )
