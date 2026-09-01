"""
Backup automatico do banco local.

O banco vive num arquivo unico em %APPDATA%, sem replica. Ate esta versao o
unico backup era manual -- e a funcao que deveria faze-lo apontava para uma
rota inexistente, entao na pratica nao havia backup nenhum.

Estes testes cobrem as duas garantias que importam: que a copia e integra e
utilizavel, e que a rotacao nao descarta justamente a copia de pre-migracao.
"""
import os
import sqlite3
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from erp.core import backup  # noqa: E402


def _banco_com_dados(caminho, quantidade=3):
    conexao = sqlite3.connect(caminho)
    with conexao:
        conexao.execute("CREATE TABLE clientes (id INTEGER PRIMARY KEY, nome TEXT)")
        conexao.executemany(
            "INSERT INTO clientes (nome) VALUES (?)",
            [(f"Cliente {i}",) for i in range(quantidade)],
        )
    conexao.close()
    return caminho


@pytest.fixture
def banco(tmp_path):
    return _banco_com_dados(str(tmp_path / "adri_poltronas.db"))


# =============================================================================
# A copia
# =============================================================================
def test_backup_gera_arquivo_integro_e_com_os_mesmos_dados(banco):
    destino = backup.criar_backup(banco, backup.MOTIVO_DIARIO)

    assert destino and os.path.exists(destino)
    copia = sqlite3.connect(destino)
    assert copia.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert copia.execute("SELECT COUNT(*) FROM clientes").fetchone()[0] == 3
    copia.close()


def test_backup_fica_em_pasta_ao_lado_do_banco(banco):
    destino = backup.criar_backup(banco, backup.MOTIVO_DIARIO)

    # Segue o banco, e nao %APPDATA% fixo: e o que permite a suite rodar sem
    # escrever na pasta real do usuario.
    assert os.path.dirname(destino) == backup.pasta_de_backups(banco)
    assert os.path.basename(os.path.dirname(destino)) == "backups"


def test_backup_nao_altera_o_banco_de_origem(banco):
    antes = os.path.getsize(banco)
    backup.criar_backup(banco, backup.MOTIVO_DIARIO)

    conexao = sqlite3.connect(banco)
    assert conexao.execute("SELECT COUNT(*) FROM clientes").fetchone()[0] == 3
    conexao.close()
    assert os.path.getsize(banco) == antes


def test_banco_inexistente_nao_gera_copia_nem_levanta(tmp_path):
    assert backup.criar_backup(str(tmp_path / "nao_existe.db"), backup.MOTIVO_DIARIO) is None


def test_falha_de_escrita_nao_derruba_o_boot(banco, monkeypatch):
    """
    Backup e rede de seguranca. Recusar a iniciar o app por causa de disco
    cheio trocaria um risco por um problema garantido.
    """
    def _explodir(*_a, **_k):
        raise OSError("disco cheio")

    monkeypatch.setattr(os, "makedirs", _explodir)
    assert backup.criar_backup(banco, backup.MOTIVO_DIARIO) is None


def test_copia_interrompida_no_meio_e_descartada(banco, monkeypatch):
    """
    Copia truncada da falsa seguranca -- e pior que copia nenhuma, porque o
    operador acha que tem de onde restaurar.

    `sqlite3.Connection.backup` e builtin e nao aceita monkeypatch, entao a
    falha e injetada envolvendo a conexao de ORIGEM, que e quem expoe o
    metodo.
    """
    conectar_original = backup.sqlite3.connect

    class _OrigemQueFalhaNaCopia:
        def __init__(self, real):
            self._real = real

        def __getattr__(self, nome):
            return getattr(self._real, nome)

        def backup(self, *_args, **_kwargs):
            raise backup.sqlite3.DatabaseError('interrompido no meio')

    def _connect(alvo, *args, **kwargs):
        real = conectar_original(alvo, *args, **kwargs)
        # So a origem (aberta por URI 'file:...?mode=ro') e sabotada.
        if isinstance(alvo, str) and alvo.startswith('file:'):
            return _OrigemQueFalhaNaCopia(real)
        return real

    monkeypatch.setattr(backup.sqlite3, 'connect', _connect)

    assert backup.criar_backup(banco, backup.MOTIVO_DIARIO) is None

    pasta = backup.pasta_de_backups(banco)
    sobraram = os.listdir(pasta) if os.path.isdir(pasta) else []
    assert sobraram == [], f"copia parcial ficou para tras: {sobraram}"


# =============================================================================
# Rotacao
# =============================================================================
def _semear(banco, motivo, quantidade):
    """
    Cria copias com carimbos crescentes controlados.

    Nomes explicitos em vez de mexer no relogio: `time.localtime` e usado por
    varias funcoes do modulo, e substitui-lo globalmente tornava o teste
    dependente da ordem interna das chamadas.
    """
    pasta = backup.pasta_de_backups(banco)
    os.makedirs(pasta, exist_ok=True)
    criados = []
    for i in range(quantidade):
        nome = f"{backup.PREFIXO}_{motivo}_202601{i + 1:02d}_120000.db"
        caminho = os.path.join(pasta, nome)
        with open(caminho, 'wb') as arquivo:
            arquivo.write(b'SQLite format 3')
        criados.append(caminho)
    return criados


def test_rotacao_respeita_o_limite_do_motivo(banco):
    limite = backup.LIMITE_POR_MOTIVO[backup.MOTIVO_DIARIO]
    _semear(banco, backup.MOTIVO_DIARIO, limite + 4)

    backup._rotacionar(backup.pasta_de_backups(banco), backup.MOTIVO_DIARIO)

    restantes = backup._copias_existentes(
        backup.pasta_de_backups(banco), backup.MOTIVO_DIARIO)
    assert len(restantes) == limite


def test_rotacao_do_diario_nao_apaga_o_de_pre_migracao(banco):
    """
    A copia de pre-migracao e a mais valiosa: e a unica que antecede uma
    mudanca de schema. Rotacionar os dois motivos juntos faria o backup
    diario expulsa-la justamente quando ela e necessaria.
    """
    criticos = _semear(banco, backup.MOTIVO_PRE_MIGRACAO, 2)
    _semear(banco, backup.MOTIVO_DIARIO, backup.LIMITE_POR_MOTIVO[backup.MOTIVO_DIARIO] + 5)

    backup._rotacionar(backup.pasta_de_backups(banco), backup.MOTIVO_DIARIO)

    assert all(os.path.exists(c) for c in criticos)


def test_rotacao_descarta_as_mais_antigas_primeiro(banco):
    limite = backup.LIMITE_POR_MOTIVO[backup.MOTIVO_PRE_MIGRACAO]
    gerados = _semear(banco, backup.MOTIVO_PRE_MIGRACAO, limite + 3)

    backup._rotacionar(backup.pasta_de_backups(banco), backup.MOTIVO_PRE_MIGRACAO)

    assert not any(os.path.exists(c) for c in gerados[:3]), "manteve as antigas"
    assert all(os.path.exists(c) for c in gerados[3:]), "descartou as recentes"


# =============================================================================
# Backup diario: uma copia por dia
# =============================================================================
def test_diario_grava_na_primeira_vez_do_dia(banco):
    assert backup.backup_diario(banco) is not None


def test_diario_nao_repete_no_mesmo_dia(banco):
    """Reabrir o app dez vezes nao pode gerar dez copias."""
    primeiro = backup.backup_diario(banco)
    assert primeiro is not None
    assert backup.backup_diario(banco) is None
    assert backup.backup_diario(banco) is None

    restantes = backup._copias_existentes(backup.pasta_de_backups(banco), backup.MOTIVO_DIARIO)
    assert len(restantes) == 1


def test_pre_migracao_nao_e_limitado_por_dia(banco):
    """Duas migrations no mesmo dia precisam de duas copias."""
    assert backup.backup_antes_de_migrar(banco) is not None
    time.sleep(1.05)  # o carimbo tem resolucao de segundo
    assert backup.backup_antes_de_migrar(banco) is not None

    restantes = backup._copias_existentes(
        backup.pasta_de_backups(banco), backup.MOTIVO_PRE_MIGRACAO)
    assert len(restantes) == 2


def test_existe_backup_de_hoje_distingue_motivo(banco):
    backup.criar_backup(banco, backup.MOTIVO_PRE_MIGRACAO)

    assert backup.existe_backup_de_hoje(banco, backup.MOTIVO_PRE_MIGRACAO) is True
    assert backup.existe_backup_de_hoje(banco, backup.MOTIVO_DIARIO) is False
