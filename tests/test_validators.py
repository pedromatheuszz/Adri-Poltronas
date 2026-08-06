"""Testes para validators."""
import sys
import os
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
