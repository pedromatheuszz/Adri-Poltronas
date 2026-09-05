"""Testes para validators."""
import sys
import os

import pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from validators import validar_cliente, normalizar_cep


def test_cliente_valido():
    dados = {
        "nome": "João Silva",
        "cep": "12345-678",
        "rua": "Rua das Flores, 123",
        "bairro": "Centro",
        "cidade": "São Paulo",
        "entrega_retirada": "Entrega",
        "observacoes": "Cliente novo",
    }
    resultado, erros = validar_cliente(dados)
    assert resultado is not None, f"Esperava sucesso, erros: {erros}"
    assert len(erros) == 0
    assert resultado["nome"] == "João Silva"
    assert resultado["cep"] == "12345-678"


def test_cliente_nome_vazio():
    dados = {
        "nome": "",
        "cep": "12345-678",
        "rua": "Rua A",
        "bairro": "Centro",
        "cidade": "SP",
        "entrega_retirada": "Entrega",
    }
    resultado, erros = validar_cliente(dados)
    assert resultado is None
    assert any("Nome" in e for e in erros)


def test_cliente_cep_invalido():
    dados = {
        "nome": "Maria",
        "cep": "000",
        "rua": "Rua A",
        "bairro": "Centro",
        "cidade": "SP",
        "entrega_retirada": "Entrega",
    }
    resultado, erros = validar_cliente(dados)
    assert resultado is None
    assert any("CEP" in e for e in erros)


def test_cliente_tipo_invalido():
    dados = {
        "nome": "Maria",
        "cep": "12345-678",
        "rua": "Rua A",
        "bairro": "Centro",
        "cidade": "SP",
        "entrega_retirada": "Invalido",
    }
    resultado, erros = validar_cliente(dados)
    assert resultado is None
    assert any("Entrega/Retirada" in e for e in erros)


def test_normalizar_cep():
    assert normalizar_cep("12345678") == "12345-678"
    assert normalizar_cep("12345-678") == "12345-678"
    assert normalizar_cep("") is None
    assert normalizar_cep(None) is None
    assert normalizar_cep("abcdef") is None


def test_cliente_observacoes_opcional():
    dados = {
        "nome": "João",
        "cep": "12345-678",
        "rua": "Rua A",
        "bairro": "Centro",
        "cidade": "SP",
        "entrega_retirada": "Retirada",
    }
    resultado, erros = validar_cliente(dados)
    assert resultado is not None
    assert resultado["observacoes"] == ""


def test_cliente_payload_nao_dict():
    resultado, erros = validar_cliente("invalido")
    assert resultado is None
    assert len(erros) > 0


# =============================================================================
# A allowlist dos campos de texto
#
# Ate a 1.3.0 a lista era `[\w\sÀ-ÿ'.,\-()/]`, e barrava razao social comum
# numa loja cuja clientela e em boa parte pessoa juridica. A recusa vinha sem
# dizer qual caractere ofendeu, entao o operador tinha de descobrir por
# tentativa e erro num campo que ele acabou de digitar.
#
# O sinal de que a regra era arbitraria, e nao de seguranca: os mesmos
# caracteres sempre passaram em `observacoes`, que nao usa esta allowlist.
# =============================================================================
def _cliente(**campos):
    base = {
        "nome": "Cliente Teste",
        "cep": "12345-678",
        "rua": "Rua A",
        "bairro": "Centro",
        "cidade": "Joinville",
        "entrega_retirada": "Entrega",
    }
    base.update(campos)
    return base


@pytest.mark.parametrize("nome", [
    "Moveis & Cia Ltda",
    "Cafe & Moveis",
    "50% Decor",
    "Loja #2",
    "Poltronas + Conforto",
])
def test_razao_social_de_pessoa_juridica_e_aceita(nome):
    resultado, erros = validar_cliente(_cliente(nome=nome))
    assert resultado is not None, f"recusou {nome!r}: {erros}"
    assert resultado["nome"] == nome


@pytest.mark.parametrize("nome", [
    "Jose D'Avila",
    "Poltronas Sao Jose S/A",
    "Anna-Lucia",
    "Movel (usado)",
])
def test_o_que_ja_era_aceito_continua_aceito(nome):
    """Ampliar a lista nao pode ter reduzido nada."""
    resultado, erros = validar_cliente(_cliente(nome=nome))
    assert resultado is not None, f"recusou {nome!r}: {erros}"


def test_payload_de_script_continua_recusado():
    """A allowlist nao e a defesa contra XSS -- `escaparHtml` e --, mas
    afrouxa-la nao pode ter aberto o caminho obvio."""
    resultado, erros = validar_cliente(_cliente(nome="<script>alert(1)</script>"))
    assert resultado is None
    assert any("Nome contem caracteres invalidos" in erro for erro in erros)


def test_a_mensagem_diz_qual_caractere_foi_recusado():
    """Sem isto o operador adivinha. E costuma ser um caractere que ele nem
    enxerga, colado de outro sistema."""
    _, erros = validar_cliente(_cliente(nome="Movel <teste>"))
    mensagem = next(erro for erro in erros if erro.startswith("Nome"))
    assert "<" in mensagem and ">" in mensagem


def test_a_mensagem_nao_devolve_o_campo_inteiro():
    """Um paragrafo colado no campo nao pode virar uma mensagem do tamanho do
    paragrafo."""
    lixo = "".join(chr(c) for c in range(33, 60)) * 3
    _, erros = validar_cliente(_cliente(nome=lixo))
    mensagem = next(erro for erro in erros if erro.startswith("Nome"))
    citados = mensagem.split(": ", 1)[1].split(" ")
    assert len(citados) <= 5


def test_as_duas_expressoes_saem_da_mesma_classe():
    """Enquanto eram literais separados, ampliar uma e esquecer a outra fazia
    a mensagem acusar caractere que a validacao aceita."""
    import validators
    for caractere in "&#+%'.,-()/ aZ9":
        aceito_inteiro = bool(validators._RE_SEGURO.match(caractere))
        aceito_avulso = bool(validators._RE_CARACTERE_SEGURO.match(caractere))
        assert aceito_inteiro == aceito_avulso, f"divergiram em {caractere!r}"
