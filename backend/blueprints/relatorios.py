# backend/blueprints/relatorios.py
"""Blueprint de relatórios."""
import time
import io
import csv
import logging
from flask import Blueprint, request, jsonify, send_file

import database
import planilha

log = logging.getLogger("adri.relatorios")

relatorios_bp = Blueprint('relatorios', __name__, url_prefix='/api/relatorios')


@relatorios_bp.route('', methods=['GET'])
def relatorios_filtrados():
    """Retorna clientes filtrados para relatórios."""
    tipo = request.args.get('tipo', '')
    cidade = request.args.get('cidade', '')
    data_inicio = request.args.get('data_inicio', '')
    data_fim = request.args.get('data_fim', '')
    clientes = database.listar_clientes_filtrados(tipo, cidade, data_inicio, data_fim)
    regioes = database.obter_perfis_regiao()
    return jsonify({"clientes": clientes, "total": len(clientes), "regioes": regioes})


@relatorios_bp.route('/exportar')
def relatorios_exportar():
    """Exporta relatório filtrado como CSV ou XLSX."""
    tipo = request.args.get('tipo', '')
    cidade = request.args.get('cidade', '')
    data_inicio = request.args.get('data_inicio', '')
    data_fim = request.args.get('data_fim', '')
    formato = request.args.get('formato', 'csv')
    clientes = database.listar_clientes_filtrados(tipo, cidade, data_inicio, data_fim)

    cabecalhos = ["Nome", "CEP", "Rua", "Bairro", "Cidade", "Entrega/Retirada", "Observacoes", "Criado em"]
    campos = ['nome', 'cep', 'rua', 'bairro', 'cidade', 'entrega_retirada', 'observacoes', 'criado_em']

    if formato == 'xlsx':
        buffer = planilha.construir_planilha("Relatorio", cabecalhos, campos, clientes)
        nome = f"relatorio_adri_{time.strftime('%Y%m%d_%H%M%S')}.xlsx"
        return send_file(buffer, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True, download_name=nome)
    else:
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(cabecalhos)
        for c in clientes:
            writer.writerow([c.get(campo, '') for campo in campos])
        buffer.seek(0)
        nome = f"relatorio_adri_{time.strftime('%Y%m%d_%H%M%S')}.csv"
        return send_file(io.BytesIO(buffer.getvalue().encode('utf-8-sig')),
            mimetype='text/csv; charset=utf-8', as_attachment=True, download_name=nome)