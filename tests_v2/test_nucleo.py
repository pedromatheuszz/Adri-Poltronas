"""Testes do nucleo: dinheiro, documento, paginacao e validacao."""
from __future__ import annotations

import pytest

from backend_v2.nucleo import documento as doc
from backend_v2.nucleo.dinheiro import ValorInvalido, formatar, para_centavos, ratear, serializar
from backend_v2.nucleo.erros import DadosInvalidos
from backend_v2.nucleo.paginacao import LIMITE_MAXIMO, Pagina
from backend_v2.nucleo.validacao import Coletor, data_valida, inteiro_positivo


# ---------------------------------------------------------------------------
# Dinheiro
# ---------------------------------------------------------------------------
@pytest.mark.parametrize('entrada,esperado', [
    ('1.234,56', 123456),      # pt-BR com separador de milhar
    ('1234.56', 123456),       # ponto decimal
    ('1234,56', 123456),       # virgula decimal
    ('R$ 99,90', 9990),        # com simbolo
    (10, 1000),                # int e UNIDADE, nao centavo
    (0.1, 10),
    ('-5,00', -500),
])
def test_conversao_para_centavos(entrada, esperado):
    assert para_centavos(entrada) == esperado


@pytest.mark.parametrize('entrada', ['', 'abc', '1.2.3', None, True])
def test_valor_mal_formado_e_recusado(entrada):
    with pytest.raises(ValorInvalido):
        para_centavos(entrada)


def test_soma_de_centavos_nao_acumula_erro_binario():
    """0.1 + 0.2 != 0.3 em float. Em centavos, e exato."""
    assert para_centavos(0.1) + para_centavos(0.2) == para_centavos(0.3)
    assert sum(para_centavos('0,01') for _ in range(100)) == para_centavos('1,00')


def test_rateio_nao_cria_nem_perde_dinheiro():
    for total in (10000, 10001, 99999, 1, 333):
        for partes in (1, 2, 3, 7, 12):
            parcelas = ratear(total, partes)
            assert len(parcelas) == partes
            assert sum(parcelas) == total, (total, partes)


def test_rateio_poe_a_sobra_na_primeira_parcela():
    """100,00 em 3: quem paga o centavo a mais paga agora, e o total fecha."""
    assert ratear(10000, 3) == [3334, 3333, 3333]


def test_formatacao_pt_br():
    assert formatar(123456) == 'R$ 1.234,56'
    assert formatar(0) == 'R$ 0,00'
    assert formatar(-500) == '-R$ 5,00'
    assert formatar(100000000) == 'R$ 1.000.000,00'


def test_serializacao_leva_inteiro_e_texto():
    saida = serializar(123456)
    assert saida == {'centavos': 123456, 'formatado': 'R$ 1.234,56'}


# ---------------------------------------------------------------------------
# Documento
# ---------------------------------------------------------------------------
@pytest.mark.parametrize('cpf,valido', [
    ('529.982.247-25', True),
    ('52998224725', True),
    ('111.111.111-11', False),   # digitos repetidos passam no "tem 11 digitos"
    ('529.982.247-26', False),   # verificador errado
    ('123', False),
])
def test_validacao_de_cpf(cpf, valido):
    assert doc.cpf_valido(cpf) is valido


@pytest.mark.parametrize('cnpj,valido', [
    ('11.222.333/0001-81', True),
    ('11222333000181', True),
    ('11.222.333/0001-82', False),
    ('00.000.000/0000-00', False),
])
def test_validacao_de_cnpj(cnpj, valido):
    assert doc.cnpj_valido(cnpj) is valido


def test_tipo_e_formatacao_de_documento():
    assert doc.tipo_documento('52998224725') == 'CPF'
    assert doc.tipo_documento('11222333000181') == 'CNPJ'
    assert doc.tipo_documento('999') is None
    assert doc.formatar('52998224725') == '529.982.247-25'
    assert doc.formatar('11222333000181') == '11.222.333/0001-81'


# ---------------------------------------------------------------------------
# Paginacao
# ---------------------------------------------------------------------------
def test_paginacao_tem_teto_e_ignora_lixo():
    assert Pagina.de_args({'limite': '99999'}).limite == LIMITE_MAXIMO
    assert Pagina.de_args({'limite': 'abc'}).limite == 50
    assert Pagina.de_args({'deslocamento': '-10'}).deslocamento == 0
    assert Pagina.de_args({'limite': '10', 'deslocamento': '20'}) == Pagina(10, 20)


# ---------------------------------------------------------------------------
# Validacao
# ---------------------------------------------------------------------------
def test_data_invalida_no_calendario_e_recusada():
    assert data_valida('2026-02-28')
    assert not data_valida('2026-02-31')   # o regex sozinho deixaria passar
    assert not data_valida('2026-13-01')
    assert not data_valida('abc')


def test_inteiro_positivo_barra_acima_do_limite_do_sqlite():
    assert inteiro_positivo('7') == 7
    assert inteiro_positivo('0') is None
    assert inteiro_positivo('-1') is None
    assert inteiro_positivo('abc') is None
    assert inteiro_positivo(10 ** 25) is None


def test_coletor_acumula_todos_os_erros():
    coletor = Coletor({'venc': '2026-13-01', 'uf': 'xyz'})
    coletor.texto('nome', obrigatorio=True, rotulo='Nome')
    coletor.data('venc', obrigatorio=True, rotulo='Vencimento')
    coletor.uf('uf', rotulo='UF')
    with pytest.raises(DadosInvalidos) as capturado:
        coletor.validar()
    assert len(capturado.value.detalhes) == 3


def test_dinheiro_aceita_forma_exata_e_humana():
    """
    `valor_centavos` (inteiro) tem prioridade sobre `valor` (unidade humana).

    Sem isso, um cliente que reenviasse o `saldo_centavos` lido da propria API
    dentro de `valor` teria o numero multiplicado por 100.
    """
    humano = Coletor({'valor': '810,00'})
    humano.dinheiro('valor', destino='valor_centavos')
    assert humano.limpo['valor_centavos'] == 81000

    exato = Coletor({'valor_centavos': 81000})
    exato.dinheiro('valor', destino='valor_centavos')
    assert exato.limpo['valor_centavos'] == 81000

    ambos = Coletor({'valor': '1,00', 'valor_centavos': 81000})
    ambos.dinheiro('valor', destino='valor_centavos')
    assert ambos.limpo['valor_centavos'] == 81000, "a forma exata deve vencer"
