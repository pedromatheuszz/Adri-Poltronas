"""
Invariantes de negocio do ERP.

Cada teste aqui protege uma regra que, se quebrar, produz numero errado no
painel ou dinheiro divergente entre modulos.
"""
from __future__ import annotations

import pytest

from backend_v2.aplicacao import cadastro, catalogo, compras, estoque, financeiro, relatorios, vendas
from backend_v2.nucleo.erros import ConflitoDeEstado, DadosInvalidos, RegraDeNegocioViolada
from backend_v2.nucleo.paginacao import Pagina
from backend_v2.infraestrutura.repo_comercial import RepositorioEstoque, RepositorioProdutos
from backend_v2.infraestrutura.repo_financeiro import RepositorioContas


# ---------------------------------------------------------------------------
# Cadastro
# ---------------------------------------------------------------------------
def test_documento_invalido_e_recusado(uow):
    with uow() as u:
        with pytest.raises(DadosInvalidos):
            cadastro.criar(u, {'nome': 'Fulano', 'documento': '111.111.111-11'})


def test_documento_duplicado_e_recusado(uow, dados_base):
    with uow() as u:
        with pytest.raises(ConflitoDeEstado):
            cadastro.criar(u, {'nome': 'Outro', 'documento': '529.982.247-25'})


def test_parceiro_precisa_de_ao_menos_um_papel(uow):
    with uow() as u:
        with pytest.raises(DadosInvalidos):
            cadastro.criar(u, {'nome': 'Ninguem', 'e_cliente': False, 'e_fornecedor': False})


def test_venda_para_quem_nao_e_cliente_e_recusada(uow, dados_base):
    with uow() as u:
        with pytest.raises(RegraDeNegocioViolada):
            vendas.criar(u, {'parceiro_id': dados_base['fornecedor']['id']})


# ---------------------------------------------------------------------------
# Estoque
# ---------------------------------------------------------------------------
def test_saldo_e_a_soma_da_razao(uow, com_estoque):
    with uow() as u:
        assert estoque.saldo(u, com_estoque['poltrona']['id'])['saldo'] == 10
        estoque.ajustar(u, {'produto_id': com_estoque['poltrona']['id'],
                            'quantidade': -3, 'observacao': 'quebra'})
        assert estoque.saldo(u, com_estoque['poltrona']['id'])['saldo'] == 7


def test_saida_maior_que_o_saldo_e_barrada(uow, com_estoque):
    with uow() as u:
        with pytest.raises(RegraDeNegocioViolada):
            estoque.registrar_movimento(
                u, produto_id=com_estoque['poltrona']['id'],
                tipo='saida_venda', quantidade=999)


def test_servico_nao_movimenta_estoque(uow, dados_base):
    with uow() as u:
        with pytest.raises(RegraDeNegocioViolada):
            estoque.registrar_movimento(
                u, produto_id=dados_base['servico']['id'],
                tipo='entrada_compra', quantidade=1)


def test_estorno_e_novo_movimento_e_nao_edicao(uow, com_estoque):
    with uow() as u:
        movimentos, _ = estoque.historico(u, com_estoque['poltrona']['id'], pagina=Pagina())
        original = movimentos[0]
        estoque.estornar_movimento(u, original['id'], 'devolucao ao fornecedor')
        # O original continua la, intocado, e o saldo voltou a zero.
        assert u.repositorio(RepositorioEstoque).buscar(original['id'])['quantidade'] == 10
        assert estoque.saldo(u, com_estoque['poltrona']['id'])['saldo'] == 0


def test_estorno_duplicado_e_recusado(uow, com_estoque):
    with uow() as u:
        movimentos, _ = estoque.historico(u, com_estoque['poltrona']['id'], pagina=Pagina())
        estoque.estornar_movimento(u, movimentos[0]['id'])
        with pytest.raises(ConflitoDeEstado):
            estoque.estornar_movimento(u, movimentos[0]['id'])


def test_custo_medio_movel_pondera_pelas_quantidades(uow, com_estoque):
    """10 a 900,00 + 10 a 1.100,00 = 20 a 1.000,00."""
    with uow() as u:
        estoque.registrar_movimento(
            u, produto_id=com_estoque['poltrona']['id'], tipo='entrada_compra',
            quantidade=10, custo_unitario_centavos=110000)
        produto = u.repositorio(RepositorioProdutos).buscar(com_estoque['poltrona']['id'])
        assert produto['custo_medio_centavos'] == 100000


def test_produto_com_saldo_nao_pode_ser_inativado(uow, com_estoque):
    with uow() as u:
        with pytest.raises(ConflitoDeEstado):
            catalogo.inativar(u, com_estoque['poltrona']['id'])


# ---------------------------------------------------------------------------
# Vendas
# ---------------------------------------------------------------------------
def _pedido_pronto(u, dados, quantidade=2):
    pedido = vendas.criar(u, {
        'parceiro_id': dados['cliente']['id'],
        'itens': [
            {'produto_id': dados['poltrona']['id'], 'quantidade': quantidade},
            {'produto_id': dados['servico']['id'], 'quantidade': 1},
        ],
    })
    vendas.abrir(u, pedido['id'])
    vendas.aprovar(u, pedido['id'])
    return pedido


def test_total_do_pedido_soma_itens(uow, com_estoque):
    with uow() as u:
        pedido = _pedido_pronto(u, com_estoque)
        # 2 x 1.890,00 + 1 x 150,00
        assert pedido['total_liquido_centavos'] == 2 * 189000 + 15000


def test_faturar_baixa_estoque_e_emite_titulos(uow, com_estoque):
    with uow() as u:
        pedido = _pedido_pronto(u, com_estoque)
        faturado = vendas.faturar(u, pedido['id'],
                                  {'parcelas': 3, 'primeiro_vencimento': '2026-09-10'})

        assert faturado['situacao'] == 'faturado'
        assert estoque.saldo(u, com_estoque['poltrona']['id'])['saldo'] == 8
        titulos = faturado['titulos_emitidos']
        assert len(titulos) == 3
        assert sum(t['valor_centavos'] for t in titulos) == faturado['total_liquido_centavos']
        # O item de servico entra no valor mas nao no saldo.
        assert len(faturado['movimentos_estoque']) == 1


def test_faturar_duas_vezes_e_recusado(uow, com_estoque):
    with uow() as u:
        pedido = _pedido_pronto(u, com_estoque)
        vendas.faturar(u, pedido['id'], {'primeiro_vencimento': '2026-09-10'})
        with pytest.raises(ConflitoDeEstado):
            vendas.faturar(u, pedido['id'], {'primeiro_vencimento': '2026-10-10'})


def test_nao_da_para_pular_etapas_da_maquina_de_estados(uow, com_estoque):
    with uow() as u:
        pedido = vendas.criar(u, {
            'parceiro_id': com_estoque['cliente']['id'],
            'itens': [{'produto_id': com_estoque['poltrona']['id'], 'quantidade': 1}],
        })
        # rascunho -> faturado nao existe
        with pytest.raises(ConflitoDeEstado):
            vendas.faturar(u, pedido['id'], {'primeiro_vencimento': '2026-09-10'})


def test_documento_faturado_nao_aceita_novos_itens(uow, com_estoque):
    with uow() as u:
        pedido = _pedido_pronto(u, com_estoque)
        vendas.faturar(u, pedido['id'], {'primeiro_vencimento': '2026-09-10'})
        with pytest.raises(ConflitoDeEstado):
            vendas.adicionar_item(u, pedido['id'],
                                  {'produto_id': com_estoque['poltrona']['id'], 'quantidade': 1})


def test_preco_do_item_fica_congelado_no_documento(uow, com_estoque):
    """Mudar o preco no catalogo nao pode reescrever documento ja emitido."""
    with uow() as u:
        pedido = _pedido_pronto(u, com_estoque, quantidade=1)
        antes = pedido['total_liquido_centavos']
        catalogo.atualizar(u, com_estoque['poltrona']['id'], {
            'codigo': 'PLT-001', 'descricao': 'Poltrona Reclinavel',
            'preco_venda': '9.999,00', 'estoque_minimo': 2,
        })
        depois = vendas.obter(u, pedido['id'])
        assert depois['total_liquido_centavos'] == antes


def test_faturamento_e_atomico(uow, dados_base):
    """
    Sem estoque, o faturamento inteiro volta atras.

    Se o estoque baixasse e a emissao de titulo falhasse, ficaria mercadoria
    saida sem cobranca -- a divergencia mais cara de achar depois.
    """
    with pytest.raises(RegraDeNegocioViolada):
        with uow() as u:
            pedido = _pedido_pronto(u, dados_base)
            vendas.faturar(u, pedido['id'], {'primeiro_vencimento': '2026-09-10'})

    with uow() as u:
        documentos, total = vendas.listar(u, pagina=Pagina())
        assert total == 0, "o documento nao pode sobreviver ao rollback"
        assert estoque.saldo(u, dados_base['poltrona']['id'])['saldo'] == 0


# ---------------------------------------------------------------------------
# Compras
# ---------------------------------------------------------------------------
def test_receber_compra_entra_estoque_e_emite_a_pagar(uow, dados_base):
    with uow() as u:
        compra = compras.criar(u, {
            'parceiro_id': dados_base['fornecedor']['id'],
            'itens': [{'produto_id': dados_base['poltrona']['id'],
                       'quantidade': 5, 'preco_unitario': '800,00'}],
        })
        compras.abrir(u, compra['id'])
        recebida = compras.receber(u, compra['id'],
                                   {'parcelas': 2, 'primeiro_vencimento': '2026-09-15'})

        assert estoque.saldo(u, dados_base['poltrona']['id'])['saldo'] == 5
        assert len(recebida['titulos_emitidos']) == 2
        assert all(t['natureza'] == 'pagar' for t in recebida['titulos_emitidos'])


def test_compra_para_quem_nao_e_fornecedor_e_recusada(uow, dados_base):
    with uow() as u:
        with pytest.raises(RegraDeNegocioViolada):
            compras.criar(u, {'parceiro_id': dados_base['cliente']['id']})


# ---------------------------------------------------------------------------
# Financeiro
# ---------------------------------------------------------------------------
def test_situacao_do_titulo_e_derivada_das_baixas(uow, com_estoque):
    with uow() as u:
        pedido = _pedido_pronto(u, com_estoque)
        faturado = vendas.faturar(u, pedido['id'], {'primeiro_vencimento': '2030-09-10'})
        titulo = faturado['titulos_emitidos'][0]
        conta = com_estoque['conta']['id']

        assert financeiro.obter_titulo(u, titulo['id'])['situacao'] == 'aberto'

        financeiro.baixar(u, titulo['id'], {'conta_id': conta, 'valor': '100,00'})
        parcial = financeiro.obter_titulo(u, titulo['id'])
        assert parcial['situacao'] == 'parcial'
        assert parcial['saldo_centavos'] == titulo['valor_centavos'] - 10000

        financeiro.baixar(u, titulo['id'],
                          {'conta_id': conta, 'valor_centavos': parcial['saldo_centavos']})
        assert financeiro.obter_titulo(u, titulo['id'])['situacao'] == 'quitado'


def test_baixa_acima_do_saldo_e_recusada(uow, com_estoque):
    with uow() as u:
        pedido = _pedido_pronto(u, com_estoque)
        faturado = vendas.faturar(u, pedido['id'], {'primeiro_vencimento': '2030-09-10'})
        titulo = faturado['titulos_emitidos'][0]
        with pytest.raises(RegraDeNegocioViolada):
            financeiro.baixar(u, titulo['id'], {
                'conta_id': com_estoque['conta']['id'],
                'valor_centavos': titulo['valor_centavos'] + 1,
            })


def test_baixa_move_o_caixa_na_mesma_transacao(uow, com_estoque):
    with uow() as u:
        pedido = _pedido_pronto(u, com_estoque)
        faturado = vendas.faturar(u, pedido['id'], {'primeiro_vencimento': '2030-09-10'})
        titulo = faturado['titulos_emitidos'][0]
        conta = com_estoque['conta']['id']

        antes = u.repositorio(RepositorioContas).saldo(conta)
        financeiro.baixar(u, titulo['id'], {'conta_id': conta, 'valor': '250,00'})
        assert u.repositorio(RepositorioContas).saldo(conta) == antes + 25000


def test_estorno_de_baixa_devolve_saldo_e_desfaz_o_caixa(uow, com_estoque):
    with uow() as u:
        pedido = _pedido_pronto(u, com_estoque)
        faturado = vendas.faturar(u, pedido['id'], {'primeiro_vencimento': '2030-09-10'})
        titulo = faturado['titulos_emitidos'][0]
        conta = com_estoque['conta']['id']

        antes = u.repositorio(RepositorioContas).saldo(conta)
        financeiro.baixar(u, titulo['id'], {'conta_id': conta, 'valor': '300,00'})
        baixa_id = financeiro.obter_titulo(u, titulo['id'])['baixas'][0]['id']

        financeiro.estornar_baixa(u, baixa_id, 'cheque devolvido')
        assert u.repositorio(RepositorioContas).saldo(conta) == antes
        assert financeiro.obter_titulo(u, titulo['id'])['situacao'] == 'aberto'


def test_titulo_com_baixa_nao_pode_ser_cancelado(uow, com_estoque):
    with uow() as u:
        pedido = _pedido_pronto(u, com_estoque)
        faturado = vendas.faturar(u, pedido['id'], {'primeiro_vencimento': '2030-09-10'})
        titulo = faturado['titulos_emitidos'][0]
        financeiro.baixar(u, titulo['id'],
                          {'conta_id': com_estoque['conta']['id'], 'valor': '50,00'})
        with pytest.raises(ConflitoDeEstado):
            financeiro.cancelar_titulo(u, titulo['id'], 'desistencia')


def test_parcelamento_respeita_fim_de_mes(uow, dados_base):
    """Dia 31 nao existe em todo mes: cai para o ultimo dia, nao estoura."""
    with uow() as u:
        titulos = financeiro.criar_titulo_avulso(u, {
            'natureza': 'pagar', 'parceiro_id': dados_base['fornecedor']['id'],
            'valor': '300,00', 'parcelas': 3, 'data_vencimento': '2026-01-31',
        })
    vencimentos = [t['data_vencimento'] for t in titulos]
    assert vencimentos == ['2026-01-31', '2026-02-28', '2026-03-31']


# ---------------------------------------------------------------------------
# Relatorios
# ---------------------------------------------------------------------------
def test_titulo_vencido_continua_contando_como_a_receber(uow, com_estoque):
    """
    Vencer nao quita nem cancela.

    No v1 o titulo marcado 'Atrasado' saia do total a receber, e o dinheiro
    ainda devido sumia do painel.
    """
    with uow() as u:
        pedido = _pedido_pronto(u, com_estoque)
        faturado = vendas.faturar(u, pedido['id'], {'primeiro_vencimento': '2020-01-10'})
        total = faturado['total_liquido_centavos']

        painel = relatorios.painel(u)
        assert painel['financeiro']['a_receber_centavos'] == total
        assert painel['financeiro']['receber_vencido_centavos'] == total


def test_painel_e_fluxo_concordam_sobre_o_saldo_em_caixa(uow, com_estoque):
    with uow() as u:
        pedido = _pedido_pronto(u, com_estoque)
        faturado = vendas.faturar(u, pedido['id'], {'primeiro_vencimento': '2030-09-10'})
        financeiro.baixar(u, faturado['titulos_emitidos'][0]['id'],
                          {'conta_id': com_estoque['conta']['id'], 'valor': '400,00'})

        painel = relatorios.painel(u)
        fluxo = relatorios.fluxo_de_caixa(u)
        assert painel['financeiro']['saldo_em_contas_centavos'] == fluxo['saldo_atual_centavos']
        assert fluxo['saldo_atual_centavos'] == 40000


def test_curva_abc_ignora_pedido_nao_faturado(uow, com_estoque):
    with uow() as u:
        _pedido_pronto(u, com_estoque)          # aprovado, nao faturado
        assert relatorios.curva_abc(u) == []

        pedido = _pedido_pronto(u, com_estoque)
        vendas.faturar(u, pedido['id'], {'primeiro_vencimento': '2030-09-10'})
        curva = relatorios.curva_abc(u)
        assert len(curva) == 2
        assert curva[0]['acumulado_pct'] <= 100.0
