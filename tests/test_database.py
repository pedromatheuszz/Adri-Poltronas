"""Testes para database usando SQLite em memória."""
import sys
import os
import tempfile
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))
from database import (
    criar_tabela, salvar_cliente, listar_clientes, obter_cliente_por_id,
    atualizar_cliente, excluir_cliente, importar_clientes_em_lote,
    excluir_sessao, salvar_sessao, obter_sessao,
)


@pytest.fixture(autouse=True)
def setup_db(monkeypatch):
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name
    monkeypatch.setattr('database.DB_PATH', db_path)
    criar_tabela()
    yield
    os.unlink(db_path)


def test_criar_e_listar_cliente():
    salvar_cliente("João", "12345-678", "Rua A", "Centro", "SP", "Entrega", "obs")
    clientes = listar_clientes()
    assert len(clientes) == 1
    assert clientes[0]["nome"] == "João"


def test_listar_clientes_com_busca():
    salvar_cliente("Maria", "11111-111", "Rua B", "Jardins", "SP", "Retirada")
    salvar_cliente("João", "22222-222", "Rua C", "Centro", "RJ", "Entrega")
    assert len(listar_clientes(busca="Maria")) == 1
    assert len(listar_clientes(busca="Centro")) == 1
    assert len(listar_clientes(busca="")) == 2


def test_obter_cliente_por_id():
    salvar_cliente("Ana", "12345-678", "Rua X", "Bairro Y", "Cidade Z", "Entrega")
    cid = listar_clientes()[0]["id"]
    assert obter_cliente_por_id(cid)["nome"] == "Ana"
    assert obter_cliente_por_id(99999) is None


def test_atualizar_cliente():
    salvar_cliente("Original", "12345-678", "Rua", "Bairro", "Cidade", "Entrega")
    cid = listar_clientes()[0]["id"]
    atualizar_cliente(cid, "Atualizado", "87654-321", "Rua Nova", "Bairro Novo", "Cidade Nova", "Retirada", "obs nova")
    assert obter_cliente_por_id(cid)["nome"] == "Atualizado"


def test_excluir_cliente():
    salvar_cliente("Teste", "12345-678", "Rua", "Bairro", "Cidade", "Entrega")
    cid = listar_clientes()[0]["id"]
    excluir_cliente(cid)
    assert len(listar_clientes()) == 0


def test_importar_lote():
    clientes = [
        {"nome": "A", "cep": "11111-111", "rua": "R1", "bairro": "B1", "cidade": "C1", "entrega_retirada": "Entrega"},
        {"nome": "B", "cep": "22222-222", "rua": "R2", "bairro": "B2", "cidade": "C2", "entrega_retirada": "Retirada"},
    ]
    r = importar_clientes_em_lote(clientes)
    assert r["sucessos"] == 2


def test_importar_lote_duplicado():
    c = [{"nome": "X", "cep": "11111-111"}]
    importar_clientes_em_lote(c)
    r = importar_clientes_em_lote(c)
    assert r["duplicados"] == 1


def test_sessao():
    salvar_sessao("token123", "user@example.com")
    s = obter_sessao()
    assert s["token"] == "token123"
    assert s["conta"] == "user@example.com"
    excluir_sessao()
    assert obter_sessao() is None

