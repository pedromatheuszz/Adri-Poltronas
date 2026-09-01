"""
Modulos colhidos do backend_v2 antes da sua remocao.

Dois nucleos que o v1 nao tinha e que o modulo de Pedido depende: dinheiro
como inteiro de centavos, e a maquina de estados do pedido.

Os testes vieram junto do codigo -- colher sem colher a cobertura seria
importar o risco e deixar a garantia para tras.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from erp.comercial import estados  # noqa: E402
from erp.core import dinheiro  # noqa: E402


# =============================================================================
# Dinheiro em centavos
# =============================================================================
@pytest.mark.parametrize('entrada, esperado', [
    ('1.234,56', 123456),   # pt-BR, como vem de planilha
    ('1234.56', 123456),    # ponto decimal
    ('R$ 99,90', 9990),     # com simbolo e espaco
    ('0,01', 1),
    ('-50,00', -5000),
    (1234.56, 123456),      # float
    (0.1, 10),
    ('10', 1000),           # sem decimais = unidade inteira
])
def test_conversao_para_centavos(entrada, esperado):
    assert dinheiro.para_centavos(entrada) == esperado


def test_int_na_borda_e_unidade_e_nao_centavos():
    """
    A armadilha documentada no modulo: `10` significa dez reais, nao dez
    centavos. Aceitar as duas leituras no mesmo lugar e como se perde dinheiro
    em integracao.
    """
    assert dinheiro.para_centavos(10) == 1000


def test_soma_longa_nao_acumula_erro_binario():
    """O motivo de existir do modulo: 0.1 + 0.2 != 0.3 em float."""
    centavos = sum(dinheiro.para_centavos('0,01') for _ in range(1000))
    assert centavos == 1000
    assert dinheiro.formatar(centavos) == 'R$ 10,00'


@pytest.mark.parametrize('invalido', ['', 'abc', 'R$', None, True, [], '1,234'])
def test_entrada_invalida_e_recusada(invalido):
    with pytest.raises((dinheiro.ValorInvalido, ValueError)):
        dinheiro.para_centavos(invalido)


@pytest.mark.parametrize('centavos, texto', [
    (123456, 'R$ 1.234,56'),
    (0, 'R$ 0,00'),
    (5, 'R$ 0,05'),
    (100000000, 'R$ 1.000.000,00'),
    (-9990, '-R$ 99,90'),
])
def test_formatacao(centavos, texto):
    assert dinheiro.formatar(centavos) == texto


# --- Rateio: o ponto onde parcelamento perde ou inventa dinheiro ------------
@pytest.mark.parametrize('total, partes', [
    (10000, 3), (10000, 7), (1, 3), (99, 4), (123456, 12), (5000, 1),
])
def test_rateio_conserva_o_total(total, partes):
    parcelas = dinheiro.ratear(total, partes)
    assert len(parcelas) == partes
    assert sum(parcelas) == total, 'o rateio criou ou sumiu com dinheiro'


def test_rateio_poe_a_sobra_na_primeira_parcela():
    """
    100,00 em 3 = 33,34 + 33,33 + 33,33. A sobra vai para a PRIMEIRA: o total
    confere ja no primeiro vencimento, em vez de depender da ultima parcela.
    """
    assert dinheiro.ratear(10000, 3) == [3334, 3333, 3333]


def test_rateio_de_valor_negativo_preserva_o_sinal():
    parcelas = dinheiro.ratear(-10000, 3)
    assert sum(parcelas) == -10000
    assert all(p < 0 for p in parcelas)


def test_rateio_em_zero_partes_e_recusado():
    with pytest.raises(dinheiro.ValorInvalido):
        dinheiro.ratear(10000, 0)


def test_serializacao_leva_inteiro_e_texto():
    """Só o formatado obrigaria o cliente a fazer parsing de moeda."""
    assert dinheiro.serializar(123456) == {'centavos': 123456, 'formatado': 'R$ 1.234,56'}


# =============================================================================
# Maquina de estados do pedido
# =============================================================================
def test_ciclo_completo_do_pedido():
    caminho = [estados.RASCUNHO, estados.ABERTO, estados.APROVADO, estados.FATURADO]
    for origem, destino in zip(caminho, caminho[1:]):
        assert estados.pode_transicionar(origem, destino), f'{origem} -> {destino}'


def test_cancelamento_possivel_ate_o_faturamento():
    for situacao in (estados.RASCUNHO, estados.ABERTO, estados.APROVADO):
        assert estados.pode_transicionar(situacao, estados.CANCELADO)


@pytest.mark.parametrize('terminal', [estados.FATURADO, estados.CANCELADO])
def test_estados_terminais_nao_saem_de_la(terminal):
    """
    Faturado ja emitiu as parcelas a receber: desfazer exige estorno
    explicito, nunca uma volta de status.
    """
    assert estados.proximos_passos(terminal) == ()


def test_nao_da_para_faturar_um_pedido_cancelado():
    """O caso que a tabela de transicoes existe para impedir."""
    assert not estados.pode_transicionar(estados.CANCELADO, estados.FATURADO)
    with pytest.raises(estados.TransicaoInvalida, match='cancelado'):
        estados.exigir_transicao(estados.CANCELADO, estados.FATURADO, 'PED-001')


def test_nao_da_para_pular_a_aprovacao():
    assert not estados.pode_transicionar(estados.ABERTO, estados.FATURADO)


def test_mensagem_de_erro_identifica_o_pedido():
    with pytest.raises(estados.TransicaoInvalida) as erro:
        estados.exigir_transicao(estados.FATURADO, estados.ABERTO, 'PED-042')
    assert 'PED-042' in str(erro.value)


def test_transicao_valida_nao_levanta():
    estados.exigir_transicao(estados.APROVADO, estados.FATURADO, 'PED-001')


def test_itens_so_sao_editaveis_antes_do_aceite():
    assert estados.e_editavel(estados.RASCUNHO)
    assert estados.e_editavel(estados.ABERTO)
    for situacao in (estados.APROVADO, estados.FATURADO, estados.CANCELADO):
        assert not estados.e_editavel(situacao)


def test_entrega_so_a_partir_da_aprovacao():
    """Antes do aceite do cliente nao ha o que entregar."""
    assert not estados.aceita_entrega(estados.RASCUNHO)
    assert not estados.aceita_entrega(estados.ABERTO)
    assert estados.aceita_entrega(estados.APROVADO)
    assert estados.aceita_entrega(estados.FATURADO)
    assert not estados.aceita_entrega(estados.CANCELADO)


def test_toda_situacao_declarada_tem_transicoes_definidas():
    """Situacao sem entrada na tabela cairia no `frozenset()` por acidente."""
    assert set(estados.TRANSICOES) == set(estados.SITUACOES)


def test_nenhuma_transicao_aponta_para_situacao_inexistente():
    for origem, destinos in estados.TRANSICOES.items():
        for destino in destinos:
            assert destino in estados.SITUACOES, f'{origem} -> {destino} nao existe'
