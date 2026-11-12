"""
A copia de seguranca sai cifrada da maquina -- literalmente.

O banco tem nome, endereco, CEP e valores a receber de clientes reais, e as
copias sao os arquivos que SAEM da pasta dele: `ADRI_BACKUP_EXTRA` as leva a
pendrive e pasta sincronizada. Ate aqui cada uma dessas copias era um SQLite
aberto por qualquer ferramenta, em qualquer maquina.

A chave e a do Fernet, que no Windows o DPAPI protege por conta. O preco
precisa estar num teste tanto quanto na documentacao: a copia so abre na
MESMA conta do Windows que a gravou. Quem leva o pendrive para outro
computador sem passar pelo download explicito descobre isso na mensagem de
erro, nao no meio de uma emergencia.
"""
import os
import sqlite3
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

import security  # noqa: E402
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
# O que sai gravado
# =============================================================================
def test_a_copia_sai_cifrada_e_nao_e_um_sqlite_legivel(banco):
    destino = backup.criar_backup(banco, backup.MOTIVO_DIARIO)

    with open(destino, "rb") as arquivo:
        inicio = arquivo.read(16)
    # Nao comeca com o magico do SQLite: abrir o pendrive com qualquer
    # ferramenta nao entrega mais nada.
    assert not inicio.startswith(b"SQLite format 3")
    assert backup._cifrada(destino) is True


def test_a_copia_cifrada_decifra_num_banco_com_os_mesmos_dados(banco, tmp_path):
    """
    Nao da para comparar BYTES com o arquivo original: o snapshot que a API
    `Connection.backup()` produz nao e byte a byte com o arquivo em disco
    (o `-wal` ainda nao foi comprimido para dentro dele). O que a copia
    precisa devolver ao decifrar e um BANCO com os mesmos dados.

    O conteudo decifrado e gravado num arquivo e aberto por ele, e nao por
    `Connection.deserialize`: esse metodo so existe a partir do Python 3.11, e
    o projeto roda tambem no 3.10 -- la o teste morria com AttributeError.
    """
    destino = backup.criar_backup(banco, backup.MOTIVO_DIARIO)

    with open(destino, encoding="ascii") as arquivo:
        conteudo = arquivo.read()
    claro = security.decifrar_bytes(conteudo)
    assert claro is not None

    decifrado = tmp_path / "decifrado.db"
    decifrado.write_bytes(claro)
    conexao = sqlite3.connect(str(decifrado))
    try:
        assert conexao.execute("SELECT COUNT(*) FROM clientes").fetchone()[0] == 3
        assert conexao.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        conexao.close()


def test_backup_em_claro_quando_nao_ha_fonte_de_chave(banco, monkeypatch):
    """
    Desenvolvimento fora do Windows, sem FERNET_KEY: a copia em claro com
    aviso no log vale mais que um backup que nao existe.
    """
    def _sem_chave():
        raise RuntimeError("nenhuma fonte de chave")

    monkeypatch.setattr(security, '_get_fernet', _sem_chave)
    destino = backup.criar_backup(banco, backup.MOTIVO_DIARIO)

    assert destino and os.path.exists(destino)
    assert backup._cifrada(destino) is False
    copia = sqlite3.connect(destino)
    assert copia.execute("SELECT COUNT(*) FROM clientes").fetchone()[0] == 3
    copia.close()


# =============================================================================
# Restauracao
# =============================================================================
def test_restaura_de_copia_cifrada(banco, tmp_path):
    destino = backup.criar_backup(banco, backup.MOTIVO_DIARIO)

    # O banco atual ganha uma linha a mais: provar que a restauracao
    # substitui, e nao soma.
    conexao = sqlite3.connect(banco)
    with conexao:
        conexao.execute("INSERT INTO clientes (nome) VALUES ('Depois da copia')")
    conexao.close()

    ok, mensagem = backup.restaurar(banco, destino)
    assert ok, mensagem

    restaurado = sqlite3.connect(banco)
    assert restaurado.execute("SELECT COUNT(*) FROM clientes").fetchone()[0] == 3
    restaurado.close()
    # O claro decifrado nao sobrevive na pasta temporaria.
    sobras = [n for n in os.listdir(backup.pasta_de_backups(banco))
              if n.endswith('.parcial')]
    assert sobras == []


def test_restaura_de_copia_legada_em_claro(banco, tmp_path):
    """
    Copias gravadas antes da cifra continuam validas: o marcador no inicio
    do arquivo e o que decide o tratamento, e quem nao o tem e SQLite puro.
    """
    legada = str(tmp_path / "backups" / f"{backup.PREFIXO}_diario_20200101_120000.db")
    os.makedirs(os.path.dirname(legada), exist_ok=True)
    conexao = sqlite3.connect(legada)
    with conexao:
        conexao.execute("CREATE TABLE historico (id INTEGER PRIMARY KEY, acao TEXT)")
        conexao.execute("INSERT INTO historico (acao) VALUES ('CRIACAO')")
    conexao.close()

    ok, mensagem = backup.restaurar(banco, legada)
    assert ok, mensagem

    restaurado = sqlite3.connect(banco)
    acoes = restaurado.execute("SELECT acao FROM historico").fetchall()
    restaurado.close()
    assert acoes == [("CRIACAO",)]


def test_copia_cifrada_com_outra_chave_e_recusada_com_mensagem_clara(banco, tmp_path):
    """
    O pendrive levado para outro computador -- ou outra conta do Windows.
    A chave de la nao decifra, e a mensagem precisa dizer ISSO: chamar de
    "corrompida" mandaria o operador procurar outra copia, quando o arquivo
    esta intacto e o problema e outro.
    """
    from cryptography.fernet import Fernet

    chave_de_outra_conta = Fernet.generate_key()
    chave_desta_conta = security._fernet_key_cache
    security._fernet_key_cache = chave_de_outra_conta
    try:
        destino = backup.criar_backup(banco, backup.MOTIVO_DIARIO)
    finally:
        security._fernet_key_cache = chave_desta_conta

    ok, mensagem = backup.restaurar(banco, destino)
    assert not ok
    assert "outra conta do Windows" in mensagem


def test_copia_adulterada_e_recusada(banco):
    destino = backup.criar_backup(banco, backup.MOTIVO_DIARIO)

    with open(destino, "a", encoding="ascii") as arquivo:
        arquivo.write("bytes pendurados no fim")

    ok, _ = backup.restaurar(banco, destino)
    assert not ok


def test_conteudo_validamente_cifrado_que_nao_e_banco_e_recusado(banco, tmp_path):
    """
    Cifra correta sobre lixo: decifra, abre... e nao e um SQLite. A copia
    de seguranca que nao e banco nao pode virar banco por magia.
    """
    falso = str(tmp_path / "backups" / f"{backup.PREFIXO}_diario_20200101_120000.db")
    os.makedirs(os.path.dirname(falso), exist_ok=True)
    with open(falso, "w", encoding="ascii") as arquivo:
        arquivo.write(security.cifrar_bytes(b"isto nao e um banco"))

    ok, mensagem = backup.restaurar(banco, falso)
    assert not ok
    assert "corrompida" in mensagem


# =============================================================================
# A lista que a tela mostra
# =============================================================================
def test_listar_copias_diz_quais_sao_cifradas(banco):
    cifrada = backup.criar_backup(banco, backup.MOTIVO_DIARIO)

    copias = backup.listar_copias(banco)
    assert copias, "nenhuma copia listada"
    por_nome = {c["arquivo"]: c for c in copias}
    assert por_nome[os.path.basename(cifrada)]["cifrada"] is True


def test_nenhuma_copia_parcial_sobrevive_ao_sucesso(banco):
    """
    O `.parcial` e o nome de construcao: ele nao pode aparecer na pasta com
    cara de copia, senao a rotacao e a lista passam a contar um arquivo que
    nao passa no integrity_check de ninguem.
    """
    backup.criar_backup(banco, backup.MOTIVO_DIARIO)

    sobras = [n for n in os.listdir(backup.pasta_de_backups(banco))
              if n.endswith(".parcial")]
    assert sobras == []
