"""Regressão: o wrapper local compartilha a chave Render canônica do projeto."""
import importlib.util
import os
from pathlib import Path


def test_chave_render_da_raiz_prevalece_sobre_copia_legada(monkeypatch):
    raiz = Path(__file__).resolve().parents[1]
    caminho = raiz / "render-api" / "config.py"
    # Valores montados por repeticao, de proposito: o teste so precisa de
    # textos com o comprimento minimo e diferentes entre si. Um literal com
    # cara de credencial reprova a varredura de segredos do CI -- foi o que
    # aconteceu com a primeira versao deste arquivo.
    monkeypatch.setenv("KEY_RENDER", "c" * 40)
    monkeypatch.setenv("RENDER_API_KEY", "l" * 40)
    monkeypatch.setenv("JWT_SECRET", "s" * 48)

    spec = importlib.util.spec_from_file_location("adri_render_api_config_test", caminho)
    assert spec and spec.loader
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)

    assert modulo.RENDER_API_KEY == os.environ["KEY_RENDER"]
