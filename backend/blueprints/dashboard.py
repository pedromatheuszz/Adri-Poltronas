# backend/blueprints/dashboard.py
"""Blueprint de dashboard (métricas e gráficos)."""
import logging
from flask import Blueprint, jsonify

import database

log = logging.getLogger("adri.dashboard")

dashboard_bp = Blueprint('dashboard', __name__, url_prefix='/api/dashboard')


@dashboard_bp.route('')
def dashboard_metricas():
    """Retorna métricas do dashboard."""
    return jsonify(database.obter_metricas_dashboard())


@dashboard_bp.route('/dados')
def dashboard_dados_graficos():
    """Retorna dados para os gráficos do dashboard."""
    por_tipo = database.obter_dados_grafico_por_tipo()
    cidades = database.obter_dados_grafico_cidades(10)
    timeline = database.obter_dados_grafico_timeline(30)
    ultimos = database.obter_ultimos_clientes(5)
    financeiro = database.obter_metricas_financeiras()
    return jsonify({
        "por_tipo": por_tipo,
        "cidades": {"labels": [c[0] for c in cidades], "valores": [c[1] for c in cidades]},
        "timeline": {"labels": [t[0] for t in timeline], "valores": [t[1] for t in timeline]},
        "ultimos_clientes": ultimos,
        "financeiro": financeiro,
    })