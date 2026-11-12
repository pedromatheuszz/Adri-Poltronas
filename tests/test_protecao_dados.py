"""
Onde o banco vive, e o que o sistema diz sobre isso.

Duas garantias:

* banco em pasta de rede e RECUSA no boot -- o SQLite sobre SMB corrompe, e
  abrir mesmo assim transforma a base de clientes num experimento;
* o disco sem BitLocker gera aviso no log de seguranca, quando ha como
  saber -- e silencio quando nao ha. Acusar sem poder examinar e o caminho
  mais curto para ensinar o operador a ignorar avisos.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from erp.core import protecao_dados  # noqa: E402


# =============================================================================
# Pasta de rede
# =============================================================================
def test_caminho_unc_e_rede():
    assert protecao_dados.em_pasta_de_rede(r'\\servidor\compartilhado\dados\base.db')


def test_pasta_local_nao_e_rede(tmp_path):
    assert protecao_dados.em_pasta_de_rede(str(tmp_path / "base.db")) is False


def test_caminho_relativo_nao_e_rede():
    assert protecao_dados.em_pasta_de_rede("base.db") is False
    assert protecao_dados.em_pasta_de_rede("") is False


def test_unidade_mapeada_e_rede(monkeypatch, tmp_path):
    """
    `Z:\\dados` so se distingue de `C:\\dados` perguntando ao Windows: no
    texto, as duas sao uma letra seguida de barra. O resolvedor real e
    injetado porque a unidade onde a suite roda e local, e criar unidade
    mapeada em CI nao e opcao.
    """
    caminho = r"Z:\dados\base.db"

    def remota(_unidade):
        return protecao_dados._DRIVE_REMOTE

    def local(_unidade):
        return 3  # DRIVE_FIXED

    def explode(_unidade):
        raise OSError("sem API")

    assert protecao_dados.em_pasta_de_rede(caminho, tipo_da_unidade=remota) is True
    assert protecao_dados.em_pasta_de_rede(caminho, tipo_da_unidade=local) is False
    # Resolvedor que explode nao pode virar excecao no boot.
    assert protecao_dados.em_pasta_de_rede(caminho, tipo_da_unidade=explode) is False


def test_rede_permitida_so_com_pedido_explicito(monkeypatch):
    monkeypatch.setenv(protecao_dados.VARIAVEL_PERMITIR_REDE, "1")
    assert protecao_dados.rede_permitida_explicitamente() is True

    monkeypatch.setenv(protecao_dados.VARIAVEL_PERMITIR_REDE, "")
    assert protecao_dados.rede_permitida_explicitamente() is False


# =============================================================================
# BitLocker: melhor esforco, resposta honesta
# =============================================================================
def _consulta(status):
    """Consultor de duble: devolve JSON como o cmdlet real."""
    def _consultar(_mount_point):
        if status is None:
            return None
        import json
        return json.dumps({"ProtectionStatus": status})
    return _consultar


def test_bitlocker_protegido_e_desprotegido_sao_lidos(tmp_path, monkeypatch):
    monkeypatch.setattr(os, "name", "nt")
    caminho = str(tmp_path / "base.db")

    assert protecao_dados.volume_com_bitlocker(caminho, consultar=_consulta(1)) is True
    assert protecao_dados.volume_com_bitlocker(caminho, consultar=_consulta(0)) is False


def test_bitlocker_indeterminavel_e_none_nao_aviso(tmp_path, monkeypatch):
    """
    Consulta que falhou, cmdlet ausente, saida ilegivel, status desconhecido:
    tudo e "nao sei", e "nao sei" nao gera aviso nenhum.
    """
    monkeypatch.setattr(os, "name", "nt")
    caminho = str(tmp_path / "base.db")

    assert protecao_dados.volume_com_bitlocker(caminho, consultar=_consulta(None)) is None
    assert protecao_dados.volume_com_bitlocker(caminho, consultar=lambda *_: "lixo") is None
    assert protecao_dados.volume_com_bitlocker(caminho, consultar=lambda *_: "") is None


def test_bitlocker_fora_do_windows_e_none(tmp_path, monkeypatch):
    monkeypatch.setattr(os, "name", "posix")
    assert protecao_dados.volume_com_bitlocker(str(tmp_path / "base.db")) is None


def test_disco_sem_bitlocker_gera_aviso_de_seguranca(tmp_path, monkeypatch):
    import security

    eventos = []
    monkeypatch.setattr(security, "log_evento_seguro",
                        lambda acao, _detalhes, _nivel="info": eventos.append(acao))

    situacao = protecao_dados.avisar_protecao_do_banco(
        str(tmp_path / "base.db"), consultar=_consulta(0))

    assert situacao["bitlocker"] is False
    assert "DISCO_SEM_BITLOCKER" in eventos


def test_bitlocker_indeterminavel_nao_gera_evento(tmp_path, monkeypatch):
    import security

    eventos = []
    monkeypatch.setattr(security, "log_evento_seguro",
                        lambda acao, _detalhes, _nivel="info": eventos.append(acao))

    protecao_dados.avisar_protecao_do_banco(
        str(tmp_path / "base.db"), consultar=_consulta(None))

    assert eventos == []


# =============================================================================
# A recusa no boot
# =============================================================================
def test_preparar_banco_recusa_pasta_de_rede(monkeypatch, tmp_path):
    """
    A recusa acontece ANTES de qualquer migration ou escrita: abrir sobre
    SMB para "ver no que da" e exatamente o experimento que a base de
    clientes nao pode financiar.
    """
    import database
    import servidor

    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "base.db"))
    monkeypatch.setattr(
        protecao_dados, "em_pasta_de_rede", lambda _caminho: True)
    monkeypatch.setenv(protecao_dados.VARIAVEL_PERMITIR_REDE, "")

    with pytest.raises(servidor.ErroDePreparacaoDoBanco) as erro:
        servidor.preparar_banco()

    assert "pasta de rede" in erro.value.resumo


def test_preparar_banco_aceita_rede_com_pedido_explicito(monkeypatch, tmp_path):
    """
    A variavel existe para o operador que decide assumir o risco por
    escrito. Ela nao pode ser um pelo-falso: com ela, o boot segue.
    """
    import database
    import servidor

    caminho = str(tmp_path / "base.db")
    monkeypatch.setattr(database, "DB_PATH", caminho)
    monkeypatch.setattr(
        protecao_dados, "em_pasta_de_rede", lambda _caminho: True)
    monkeypatch.setenv(protecao_dados.VARIAVEL_PERMITIR_REDE, "1")

    # Banco novo, vazio: o caminho legitimo de instalacao limpa.
    servidor.preparar_banco()
    assert os.path.exists(caminho)
