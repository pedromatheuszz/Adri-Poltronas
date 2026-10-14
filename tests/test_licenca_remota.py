"""Testes unitários do cliente da API central de licenças (licenca_remota.py)."""
import json
import os
import sys
from datetime import datetime, timedelta

import pytest

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(RAIZ, "backend"))

import database  # noqa: E402
import licenca  # noqa: E402
import licenca_remota  # noqa: E402
import segredos  # noqa: E402


@pytest.fixture
def banco_limpo(tmp_path, monkeypatch):
    banco = str(tmp_path / "teste_remota.db")
    monkeypatch.setenv("ADRI_DB_PATH", banco)
    monkeypatch.setattr(database, "DB_PATH", banco)
    database.criar_tabela()
    return banco


def test_url_segura_aceita_apenas_https_ou_loopback():
    assert licenca_remota._url_segura("https://licencas.exemplo.com") is True
    assert licenca_remota._url_segura("https://adri-licencas.onrender.com") is True
    assert licenca_remota._url_segura("http://localhost:8080") is True
    assert licenca_remota._url_segura("http://127.0.0.1:5000") is True
    assert licenca_remota._url_segura("http://inseguro.exemplo.com") is False
    assert licenca_remota._url_segura("ftp://licencas.exemplo.com") is False


def test_url_insegura_levanta_excecao(monkeypatch):
    monkeypatch.setenv("ADRI_LICENCA_API_URL", "http://inseguro.exemplo.com")
    with pytest.raises(RuntimeError, match="HTTPS"):
        licenca_remota._requisicao("/v1/licenses/sync", {})


def test_normalizar_calcula_dias_e_estados():
    agora = datetime.now()
    expira_futuro = (agora + timedelta(days=15)).strftime("%Y-%m-%dT%H:%M:%SZ")

    res_trial = licenca_remota._normalizar({
        "estado": "trial",
        "expira_em": expira_futuro,
    })
    assert res_trial["estado"] == "teste"
    assert res_trial["dias_restantes"] >= 14
    assert res_trial["valor_centavos"] == licenca.VALOR_DA_LICENCA_CENTAVOS

    res_paid = licenca_remota._normalizar({"estado": "paid"})
    assert res_paid["estado"] == "paga"
    assert res_paid["dias_restantes"] is None

    expira_passado = (agora - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    res_expirada = licenca_remota._normalizar({
        "estado": "trial",
        "expira_em": expira_passado,
    })
    assert res_expirada["estado"] == "expirada"
    assert res_expirada["dias_restantes"] == 0


def test_situacao_em_cache_respeita_tolerancia_72h(banco_limpo):
    user_id = database.criar_usuario("cliente_cache", "senha12345678", "usuario", "cliente@teste.com")
    agora = datetime.now()

    # Cache válido dentro de 72h
    database.gravar_licenca_remota(user_id, {
        "estado_central": "trial",
        "expira_em": (agora + timedelta(days=10)).strftime("%Y-%m-%dT%H:%M:%S"),
        "verificada_em": agora.strftime("%Y-%m-%dT%H:%M:%S"),
        "offline_ate": (agora + timedelta(hours=48)).strftime("%Y-%m-%dT%H:%M:%S"),
    })
    cache = licenca_remota.situacao_em_cache(user_id)
    assert cache is not None
    assert cache["estado"] == "teste"
    assert cache["dias_restantes"] > 0
    assert cache["valor_centavos"] == licenca.VALOR_DA_LICENCA_CENTAVOS

    # Cache após expiração da tolerância offline (mais de 72h)
    database.gravar_licenca_remota(user_id, {
        "estado_central": "trial",
        "expira_em": (agora + timedelta(days=10)).strftime("%Y-%m-%dT%H:%M:%S"),
        "verificada_em": (agora - timedelta(hours=80)).strftime("%Y-%m-%dT%H:%M:%S"),
        "offline_ate": (agora - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%S"),
    })
    cache_expirado = licenca_remota.situacao_em_cache(user_id)
    assert cache_expirado["estado"] == "expirada"
    assert cache_expirado["dias_restantes"] == 0


def test_sincronizacao_falha_segura_quando_offline(banco_limpo, monkeypatch):
    monkeypatch.setenv("ADRI_LICENCA_API_URL", "https://licencas.offline.local")
    user_id = database.criar_usuario("cliente_offline", "senha12345678", "usuario")

    # Quando a rede falha, sincronizar_usuario retorna None sem quebrar o app
    resultado = licenca_remota.sincronizar_usuario(user_id)
    assert resultado is None


def test_acoes_admin_validam_parametros(monkeypatch):
    monkeypatch.setenv("ADRI_LICENCA_API_URL", "https://licencas.teste.local")
    monkeypatch.setattr(segredos, "obter", lambda _: "token_secreto_valido_com_mais_de_quarenta_caracteres_123456789")

    with pytest.raises(ValueError, match="Ação de licença inválida"):
        licenca_remota.controlar_conta_admin("id-123", "acao_desconhecida")

    with pytest.raises(ValueError, match="Identificador de licença inválido"):
        licenca_remota.controlar_conta_admin("id com espaços inválidos!", "paid")
