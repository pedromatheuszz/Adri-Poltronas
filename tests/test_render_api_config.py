"""Regressão: o wrapper local compartilha a chave Render canônica do projeto."""
import importlib.util
import os
from pathlib import Path


def test_chave_render_da_raiz_prevalece_sobre_copia_legada(monkeypatch):
    raiz = Path(__file__).resolve().parents[1]
    caminho = raiz / "render-api" / "config.py"
    monkeypatch.setenv("KEY_RENDER", "chave-canonica-ficticia-comprida-123456")
    monkeypatch.setenv("RENDER_API_KEY", "chave-legada-ficticia-comprida-654321")
    monkeypatch.setenv("JWT_SECRET", "segredo-ficticio-de-teste-com-mais-de-32-caracteres")

    spec = importlib.util.spec_from_file_location("adri_render_api_config_test", caminho)
    assert spec and spec.loader
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)

    assert modulo.RENDER_API_KEY == os.environ["KEY_RENDER"]
