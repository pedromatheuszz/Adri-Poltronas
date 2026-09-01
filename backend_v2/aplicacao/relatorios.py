"""
Indicadores gerenciais.

Uma unica fonte por numero. No v1 'atrasado' tinha duas definicoes diferentes
em dois blocos de metricas, e os dois cards do painel discordavam. Aqui cada
indicador sai de uma consulta so, e as que compartilham conceito compartilham
o mesmo SQL.
"""
from __future__ import annotations

from datetime import date, timedelta

from backend_v2.infraestrutura.repo_financeiro import RepositorioCaixa, RepositorioContas, RepositorioTitulos


def _hoje() -> str:
    return date.today().isoformat()


def painel(unidade) -> dict:
    """Visao geral: comercial, estoque e financeiro num retrato so."""
    conexao = unidade.conexao

    def escalar(sql, parametros=()):
        linha = conexao.execute(sql, parametros).fetchone()
        return linha[0] if linha else 0

    comercial = {
        'parceiros_ativos': escalar("SELECT COUNT(*) FROM parceiros WHERE ativo=1"),
        'clientes': escalar("SELECT COUNT(*) FROM parceiros WHERE ativo=1 AND e_cliente=1"),
        'fornecedores': escalar("SELECT COUNT(*) FROM parceiros WHERE ativo=1 AND e_fornecedor=1"),
        'orcamentos_abertos': escalar(
            "SELECT COUNT(*) FROM documentos_venda WHERE especie='orcamento' "
            "AND situacao IN ('rascunho','aberto','aprovado')"),
        'pedidos_a_faturar': escalar(
            "SELECT COUNT(*) FROM documentos_venda WHERE situacao='aprovado'"),
        'faturado_mes_centavos': escalar(
            "SELECT COALESCE(SUM(total_liquido_centavos), 0) FROM documentos_venda "
            "WHERE situacao='faturado' "
            "AND strftime('%Y-%m', faturado_em) = strftime('%Y-%m', date('now','localtime'))"),
    }

    estoque = {
        'produtos_ativos': escalar("SELECT COUNT(*) FROM produtos WHERE ativo=1"),
        'itens_abaixo_do_minimo': escalar(
            "SELECT COUNT(*) FROM estoque_saldos WHERE abaixo_do_minimo=1"),
        # Valor do estoque ao custo medio: o que esta parado em dinheiro.
        'valor_ao_custo_centavos': escalar(
            "SELECT COALESCE(SUM(s.saldo * p.custo_medio_centavos), 0) "
            "  FROM estoque_saldos s JOIN produtos p ON p.id = s.produto_id "
            " WHERE s.saldo > 0"),
    }

    titulos = unidade.repositorio(RepositorioTitulos)
    receber = titulos.totais_por_situacao('receber')
    pagar = titulos.totais_por_situacao('pagar')

    def somar(mapa, *situacoes):
        return sum(int(mapa.get(s, {}).get('saldo_centavos', 0)) for s in situacoes)

    contas = unidade.repositorio(RepositorioContas).listar_com_saldo()
    financeiro = {
        # 'aberto' e 'vencido' e 'parcial' sao todos saldo a receber: vencer
        # nao quita nem cancela. Foi o erro oposto do v1, onde o titulo
        # marcado 'Atrasado' sumia do total a receber.
        'a_receber_centavos': somar(receber, 'aberto', 'vencido', 'parcial'),
        'receber_vencido_centavos': somar(receber, 'vencido'),
        'a_pagar_centavos': somar(pagar, 'aberto', 'vencido', 'parcial'),
        'pagar_vencido_centavos': somar(pagar, 'vencido'),
        'saldo_em_contas_centavos': sum(int(c['saldo_centavos']) for c in contas),
        'contas': contas,
    }

    operacional = {
        'entregas_hoje': escalar(
            "SELECT COUNT(*) FROM entregas WHERE data_prevista = date('now','localtime') "
            "AND situacao NOT IN ('concluida','cancelada')"),
        'entregas_atrasadas': escalar(
            "SELECT COUNT(*) FROM entregas WHERE data_prevista < date('now','localtime') "
            "AND situacao NOT IN ('concluida','cancelada')"),
    }

    return {
        'data': _hoje(),
        'comercial': comercial,
        'estoque': estoque,
        'financeiro': financeiro,
        'operacional': operacional,
    }


def fluxo_de_caixa(unidade, *, dias: int = 30) -> dict:
    """
    Realizado (movimento de caixa) + previsto (titulos em aberto por vencimento).

    Os dois lado a lado: o realizado responde "quanto entrou", o previsto
    responde "quanto deve entrar" -- e e a diferenca entre eles que antecipa
    aperto de caixa.
    """
    hoje = date.today()
    inicio = (hoje - timedelta(days=dias)).isoformat()
    fim_previsao = (hoje + timedelta(days=dias)).isoformat()

    realizado = unidade.repositorio(RepositorioCaixa).fluxo_por_dia(inicio, hoje.isoformat())

    previsto = [dict(linha) for linha in unidade.conexao.execute(
        "SELECT data_vencimento AS dia, "
        "       COALESCE(SUM(CASE WHEN natureza='receber' THEN saldo_centavos END), 0) AS a_receber, "
        "       COALESCE(SUM(CASE WHEN natureza='pagar'   THEN saldo_centavos END), 0) AS a_pagar "
        "  FROM titulos_situacao "
        " WHERE cancelado = 0 AND situacao IN ('aberto','vencido','parcial') "
        "   AND data_vencimento BETWEEN ? AND ? "
        " GROUP BY data_vencimento ORDER BY data_vencimento",
        (hoje.isoformat(), fim_previsao),
    ).fetchall()]

    for linha in previsto:
        linha['liquido_previsto_centavos'] = int(linha['a_receber']) - int(linha['a_pagar'])
        linha['a_receber_centavos'] = int(linha.pop('a_receber'))
        linha['a_pagar_centavos'] = int(linha.pop('a_pagar'))

    saldo_atual = sum(
        int(c['saldo_centavos'])
        for c in unidade.repositorio(RepositorioContas).listar_com_saldo()
    )
    return {
        'saldo_atual_centavos': saldo_atual,
        'periodo_realizado': {'de': inicio, 'ate': hoje.isoformat()},
        'periodo_previsto': {'de': hoje.isoformat(), 'ate': fim_previsao},
        'realizado': [
            {
                'dia': linha['dia'],
                'entradas_centavos': int(linha['entradas']),
                'saidas_centavos': int(linha['saidas']),
                'liquido_centavos': int(linha['liquido']),
            }
            for linha in realizado
        ],
        'previsto': previsto,
    }


def curva_abc(unidade, *, limite: int = 20) -> list[dict]:
    """
    Produtos por faturamento, so de documentos FATURADOS.

    Orcamento e pedido em aberto ainda podem virar nada; contar os dois na
    curva inflaria o ranking com venda que nunca aconteceu.
    """
    linhas = unidade.conexao.execute(
        "SELECT i.produto_id, i.descricao, "
        "       SUM(i.quantidade) AS quantidade, "
        "       SUM(i.total_centavos) AS faturado_centavos "
        "  FROM documentos_venda_itens i "
        "  JOIN documentos_venda d ON d.id = i.documento_id "
        " WHERE d.situacao = 'faturado' "
        " GROUP BY i.produto_id, i.descricao "
        " ORDER BY faturado_centavos DESC LIMIT ?",
        (limite,),
    ).fetchall()
    total = sum(int(linha['faturado_centavos']) for linha in linhas) or 1
    acumulado = 0
    resultado = []
    for linha in linhas:
        valor = int(linha['faturado_centavos'])
        acumulado += valor
        resultado.append({
            'produto_id': linha['produto_id'],
            'descricao': linha['descricao'],
            'quantidade': int(linha['quantidade']),
            'faturado_centavos': valor,
            'participacao_pct': round(valor * 100 / total, 2),
            'acumulado_pct': round(acumulado * 100 / total, 2),
        })
    return resultado
