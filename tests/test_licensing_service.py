"""Testes da API central de licenças (licensing-service/app.py)."""
import hashlib
import sys
import types
from unittest.mock import MagicMock

import pytest

# Se psycopg não estiver instalado no ambiente do ERP (que usa SQLite),
# registra um dublê em sys.modules para permitir testar as rotas do Flask.
if "psycopg" not in sys.modules:
    mock_psycopg = types.ModuleType("psycopg")
    mock_rows = types.ModuleType("psycopg.rows")
    mock_rows.dict_row = MagicMock()
    mock_psycopg.rows = mock_rows
    mock_psycopg.connect = MagicMock()
    sys.modules["psycopg"] = mock_psycopg
    sys.modules["psycopg.rows"] = mock_rows

import importlib.util
import os

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PASTA_SERVICO = os.path.join(RAIZ, "licensing-service")
CAMINHO_APP = os.path.join(PASTA_SERVICO, "app.py")

spec = importlib.util.spec_from_file_location("licensing_service_app", CAMINHO_APP)
licensing_app = importlib.util.module_from_spec(spec)
sys.modules["licensing_service_app"] = licensing_app
spec.loader.exec_module(licensing_app)


TOKEN_ADMIN_TESTE = "token_de_teste_muito_seguro_e_com_mais_de_quarenta_caracteres_123"


@pytest.fixture
def cliente_api(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/db")
    monkeypatch.setenv("LICENSE_ADMIN_TOKEN", TOKEN_ADMIN_TESTE)
    licensing_app._schema_ready = True  # Marca schema como inicializado para testes unitários
    licensing_app.app.config["TESTING"] = True
    with licensing_app.app.test_client() as client:
        yield client


def test_health_retorna_ok_quando_banco_responde(cliente_api, monkeypatch):
    mock_conn = MagicMock()
    monkeypatch.setattr(licensing_app, "_db", lambda: mock_conn)
    mock_conn.__enter__.return_value = mock_conn

    res = cliente_api.get("/health")
    assert res.status_code == 200
    dados = res.get_json()
    assert dados["status"] == "ok"
    assert dados["service"] == "adri-licensing"


def test_health_retorna_503_quando_banco_falha(cliente_api, monkeypatch):
    def falhar_conexao():
        raise RuntimeError("Banco inacessível")

    monkeypatch.setattr(licensing_app, "_db", falhar_conexao)

    res = cliente_api.get("/health")
    assert res.status_code == 503
    dados = res.get_json()
    assert dados["status"] == "degraded"


def test_sync_rejeita_parametros_invalidos(cliente_api):
    # ID com caractere inválido
    res = cliente_api.post("/v1/licenses/sync", json={
        "license_id": "id com espaço",
        "client_secret": "a" * 40,
        "username": "Cliente",
    })
    assert res.status_code == 400

    # Segredo muito curto (< 40 caracteres)
    res = cliente_api.post("/v1/licenses/sync", json={
        "license_id": "id-valido-123",
        "client_secret": "curto",
        "username": "Cliente",
    })
    assert res.status_code == 400

    # Username vazio
    res = cliente_api.post("/v1/licenses/sync", json={
        "license_id": "id-valido-123",
        "client_secret": "a" * 40,
        "username": "   ",
    })
    assert res.status_code == 400


def test_admin_exige_autorizacao_bearer(cliente_api):
    res = cliente_api.get("/v1/admin/licenses")
    assert res.status_code == 401

    res_invalido = cliente_api.get("/v1/admin/licenses", headers={"Authorization": "Bearer token_errado"})
    assert res_invalido.status_code == 401


def test_admin_lista_contas_com_token_valido(cliente_api, monkeypatch):
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.fetchall.return_value = []
    mock_conn.execute.return_value = mock_cursor
    mock_conn.__enter__.return_value = mock_conn
    monkeypatch.setattr(licensing_app, "_db", lambda: mock_conn)

    res = cliente_api.get(
        "/v1/admin/licenses",
        headers={"Authorization": f"Bearer {TOKEN_ADMIN_TESTE}"},
    )
    assert res.status_code == 200
    assert res.get_json() == {"contas": []}
