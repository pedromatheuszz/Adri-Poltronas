# tests/test_api.py
"""Testes de API Flask."""
import sys
import os
import json
import tempfile
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

import database
import app as app_module


@pytest.fixture
def app():
    """Cria uma instância de teste da aplicação."""
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name
    
    # Monkey patch para usar banco de testes
    original_db_path = database.DB_PATH
    database.DB_PATH = db_path
    
    app_instance = app_module.app
    app_instance.config['TESTING'] = True
    
    with app_instance.app_context():
        database.criar_tabela()
    
    yield app_instance
    
    database.DB_PATH = original_db_path
    os.unlink(db_path)


@pytest.fixture
def client(app):
    """Cria um cliente de teste."""
    return app.test_client()


def test_index_page(client):
    """Testa a página inicial."""
    response = client.get('/')
    assert response.status_code == 200


def test_listar_clientes_vazio(client):
    """Testa listar clientes quando não há nenhum."""
    response = client.get('/api/clientes')
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data == []


def test_adicionar_cliente(client):
    """Testa adicionar um novo cliente."""
    cliente_data = {
        "nome": "João Silva",
        "cep": "12345-678",
        "rua": "Rua das Flores",
        "bairro": "Centro",
        "cidade": "São Paulo",
        "entrega_retirada": "Entrega",
        "observacoes": "Cliente teste"
    }
    response = client.post('/api/clientes', 
        data=json.dumps(cliente_data),
        content_type='application/json')
    assert response.status_code == 201
    data = json.loads(response.data)
    assert data["mensagem"] == "Cliente cadastrado!"


def test_adicionar_cliente_inválido(client):
    """Testa adicionar cliente com dados inválidos."""
    cliente_data = {
        "nome": "",
        "cep": "12345-678",
    }
    response = client.post('/api/clientes',
        data=json.dumps(cliente_data),
        content_type='application/json')
    assert response.status_code == 400
    data = json.loads(response.data)
    assert "erro" in data


def test_dashboard_metricas(client):
    """Testa obter métricas do dashboard."""
    response = client.get('/api/dashboard')
    assert response.status_code == 200
    data = json.loads(response.data)
    assert "total_clientes" in data
    assert data["total_clientes"] == 0


def test_status_autenticacao_sem_sessao(client):
    """Testa status de autenticação sem sessão."""
    response = client.get('/api/auth/status')
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data["logado"] is False


def test_manifest_json(client):
    """Testa acesso ao manifest.json."""
    response = client.get('/manifest.json')
    assert response.status_code == 200


def test_service_worker(client):
    """Testa acesso ao service worker."""
    response = client.get('/sw.js')
    assert response.status_code == 200


def test_criar_pagamento(client):
    """Testa criar um pagamento."""
    # Primeiro, criar um cliente
    cliente_data = {
        "nome": "Cliente Teste",
        "cep": "12345-678",
        "rua": "Rua Teste",
        "bairro": "Centro",
        "cidade": "São Paulo",
        "entrega_retirada": "Entrega"
    }
    client.post('/api/clientes',
        data=json.dumps(cliente_data),
        content_type='application/json')
    
    # Obter cliente criado
    response = client.get('/api/clientes')
    clientes = json.loads(response.data)
    cliente_id = clientes[0]['id']
    
    # Criar pagamento
    pagamento_data = {
        "cliente_id": cliente_id,
        "cliente_nome": "Cliente Teste",
        "valor": 100.50,
        "descricao": "Pagamento teste",
        "data_vencimento": "2026-08-15",
        "tipo_pagamento": "Pix"
    }
    response = client.post('/api/pagamentos',
        data=json.dumps(pagamento_data),
        content_type='application/json')
    assert response.status_code == 201
    data = json.loads(response.data)
    assert "id" in data


def test_listar_pagamentos(client):
    """Testa listar pagamentos."""
    response = client.get('/api/pagamentos')
    assert response.status_code == 200
    data = json.loads(response.data)
    assert isinstance(data, list)


def test_pagamentos_metricas(client):
    """Testa métricas de pagamentos."""
    response = client.get('/api/pagamentos/metricas')
    assert response.status_code == 200
    data = json.loads(response.data)
    assert "total_recebido" in data
    assert "total_pendente" in data


def test_notificacoes(client):
    """Testa obter notificações."""
    response = client.get('/api/notificacoes')
    assert response.status_code == 200
    data = json.loads(response.data)
    assert "notificacoes" in data
    assert isinstance(data["notificacoes"], list)
