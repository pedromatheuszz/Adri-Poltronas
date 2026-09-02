"""
O que acontece quando preparar o banco da errado.

Ate a versao 1.1 a resposta era sempre a mesma: seguir em frente. O backup de
pre-migracao falhava e a migracao rodava assim mesmo; a migracao morria no
meio e o schema fallback era aplicado POR CIMA do banco parcialmente migrado,
com o app subindo como se nada tivesse acontecido. Nos dois caminhos, um erro
recuperavel virava perda silenciosa de dado.

A regra agora depende de uma unica pergunta -- ha dado a perder?

* Banco novo ou vazio: o fallback continua legitimo. Nada a corromper, e uma
  instalacao sem alembic legivel ainda sobe com o schema basico.
* Banco com dados: falha e falha. O processo se recusa a subir e devolve
  instrucoes de recuperacao.

O teste do banco legado e o mais importante do arquivo: era o caso em que a
versao anterior respondia "nao ha migracao pendente" -- e migrava sem backup
justamente o banco cheio de clientes reais.
"""
import os
import sqlite3
import sys

import pytest

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(RAIZ, 'backend'))

import database  # noqa: E402
import migrations_manager  # noqa: E402
import servidor  # noqa: E402
from erp.core import backup  # noqa: E402


def _apontar_para(monkeypatch, caminho):
    """Faz todo o backend enxergar `caminho` como o banco da instalacao."""
    monkeypatch.setattr(database, 'obter_caminho_banco_absoluto', lambda: str(caminho))


def _banco_legado(caminho):
    """Banco com dados de verdade e sem `alembic_version` -- o estado em que
    uma instalacao anterior ao Alembic chega numa atualizacao."""
    conexao = sqlite3.connect(str(caminho))
    with conexao:
        conexao.execute("CREATE TABLE clientes (id INTEGER PRIMARY KEY, nome TEXT)")
        conexao.execute("INSERT INTO clientes (nome) VALUES ('Cliente Real')")
    conexao.close()
    return caminho


def _banco_versionado(caminho, revisao="d1e7b3f5620a"):
    conexao = sqlite3.connect(str(caminho))
    with conexao:
        conexao.execute("CREATE TABLE clientes (id INTEGER PRIMARY KEY, nome TEXT)")
        conexao.execute("CREATE TABLE alembic_version (version_num TEXT NOT NULL)")
        conexao.execute("INSERT INTO alembic_version VALUES (?)", (revisao,))
    conexao.close()
    return caminho


# =============================================================================
# Classificacao do arquivo
# =============================================================================
def test_arquivo_inexistente_e_ausente(monkeypatch, tmp_path):
    _apontar_para(monkeypatch, tmp_path / "nao_existe.db")
    assert migrations_manager.estado_do_banco() == migrations_manager.ESTADO_AUSENTE
    assert migrations_manager.banco_tem_dados() is False


def test_arquivo_zerado_e_ausente(monkeypatch, tmp_path):
    """Um .db de zero byte e o que sobra de uma criacao interrompida: nao tem
    schema, nao tem dado, e tratar como 'existe' bloquearia a instalacao."""
    caminho = tmp_path / "vazio.db"
    caminho.write_bytes(b"")
    _apontar_para(monkeypatch, caminho)
    assert migrations_manager.estado_do_banco() == migrations_manager.ESTADO_AUSENTE


def test_banco_com_header_e_sem_tabelas_e_vazio(monkeypatch, tmp_path):
    """Arquivo ja escrito pelo SQLite, mas sem nenhuma tabela do usuario.

    Um `connect()` puro nao serve para montar este caso: o SQLite so grava o
    header no primeiro write, entao o arquivo fica com zero byte e e
    indistinguivel de inexistente -- o que, para efeito de decisao, ele e.
    """
    caminho = tmp_path / "novo.db"
    conexao = sqlite3.connect(str(caminho))
    with conexao:
        conexao.execute("CREATE TABLE rascunho (id INTEGER)")
        conexao.execute("DROP TABLE rascunho")
    conexao.close()

    _apontar_para(monkeypatch, caminho)
    assert migrations_manager.estado_do_banco() == migrations_manager.ESTADO_VAZIO
    assert migrations_manager.banco_tem_dados() is False


def test_banco_com_tabelas_e_sem_alembic_version_e_legado(monkeypatch, tmp_path):
    _apontar_para(monkeypatch, _banco_legado(tmp_path / "legado.db"))
    assert migrations_manager.estado_do_banco() == migrations_manager.ESTADO_LEGADO
    assert migrations_manager.banco_tem_dados() is True


def test_banco_corrompido_e_ilegivel(monkeypatch, tmp_path):
    caminho = tmp_path / "corrompido.db"
    caminho.write_bytes(b"isto nao e um banco sqlite" * 20)
    _apontar_para(monkeypatch, caminho)
    assert migrations_manager.estado_do_banco() == migrations_manager.ESTADO_ILEGIVEL
    assert migrations_manager.banco_tem_dados() is True


# =============================================================================
# O gatilho do backup
# =============================================================================
def test_banco_legado_exige_backup_antes_de_migrar(monkeypatch, tmp_path):
    """A regressao que motivou este arquivo.

    `revisao_do_banco()` devolvia None para banco legado, banco ausente e
    banco ilegivel -- e `ha_migracoes_pendentes()` lia esse None como "nao ha
    nada pendente". O banco com mais a perder era o unico que migrava sem
    copia previa.
    """
    _apontar_para(monkeypatch, _banco_legado(tmp_path / "legado.db"))
    assert migrations_manager.ha_migracoes_pendentes() is True


def test_banco_novo_nao_dispara_backup(monkeypatch, tmp_path):
    _apontar_para(monkeypatch, tmp_path / "nao_existe.db")
    assert migrations_manager.ha_migracoes_pendentes() is False


def test_banco_ja_na_cabeca_nao_dispara_backup(monkeypatch, tmp_path):
    alvo = migrations_manager.revisao_alvo()
    assert alvo, "a cadeia de migrations precisa ter uma cabeca"
    _apontar_para(monkeypatch, _banco_versionado(tmp_path / "atual.db", alvo))
    assert migrations_manager.ha_migracoes_pendentes() is False


# =============================================================================
# preparar_banco(): a decisao depende de haver dado a perder
# =============================================================================
def test_banco_novo_cai_para_o_schema_basico_quando_a_migracao_falha(monkeypatch, tmp_path):
    """Instalacao nova sem alembic legivel precisa subir com o schema basico:
    a janela vazia nao diz nada ao operador, e nao ha dado em risco."""
    _apontar_para(monkeypatch, tmp_path / "novo.db")

    def explode():
        raise RuntimeError('alembic.ini ausente')

    chamou = []
    monkeypatch.setattr(migrations_manager, 'aplicar_migrações', explode)
    monkeypatch.setattr(database, 'criar_tabela', lambda: chamou.append(True))

    servidor.preparar_banco()

    assert chamou == [True]


def test_banco_com_dados_recusa_subir_quando_a_migracao_falha(monkeypatch, tmp_path):
    """Aqui o fallback seria destrutivo: rodaria CREATE TABLE por cima de um
    banco que pode ter ficado no meio da migracao."""
    _apontar_para(monkeypatch, _banco_versionado(tmp_path / "producao.db", "b5a1c7e94d20"))

    def explode():
        raise RuntimeError('migration quebrou no meio')

    chamou = []
    monkeypatch.setattr(migrations_manager, 'aplicar_migrações', explode)
    monkeypatch.setattr(database, 'criar_tabela', lambda: chamou.append(True))

    with pytest.raises(servidor.ErroDePreparacaoDoBanco):
        servidor.preparar_banco()

    assert chamou == [], "o schema fallback nao pode tocar um banco com dados"


def test_banco_com_dados_recusa_migrar_sem_backup(monkeypatch, tmp_path):
    """Migrar sem rede sobre dado real e o que transforma um erro recuperavel
    em perda definitiva."""
    _apontar_para(monkeypatch, _banco_versionado(tmp_path / "producao.db", "b5a1c7e94d20"))

    migrou = []
    monkeypatch.setattr(backup, 'backup_antes_de_migrar', lambda _c: None)
    monkeypatch.setattr(migrations_manager, 'aplicar_migrações', lambda: migrou.append(True))

    with pytest.raises(servidor.ErroDePreparacaoDoBanco):
        servidor.preparar_banco()

    assert migrou == [], "sem backup, a migracao nao pode nem comecar"


def test_banco_ilegivel_recusa_subir(monkeypatch, tmp_path):
    caminho = tmp_path / "corrompido.db"
    caminho.write_bytes(b"lixo binario" * 50)
    _apontar_para(monkeypatch, caminho)

    with pytest.raises(servidor.ErroDePreparacaoDoBanco):
        servidor.preparar_banco()


def test_instrucoes_apontam_o_caminho_de_volta(tmp_path):
    """A mensagem e a unica coisa que o operador vai ler. Sem a pasta das
    copias ela informa um problema e nao oferece saida."""
    banco = str(tmp_path / "adri_poltronas.db")
    erro = servidor.ErroDePreparacaoDoBanco("A migracao falhou.", banco)
    texto = erro.instrucoes()

    assert "A migracao falhou." in texto
    assert banco in texto
    assert backup.pasta_de_backups(banco) in texto
    assert "Restaure" in texto


# =============================================================================
# main(): sai com codigo proprio e deixa o rastro que o Electron le
# =============================================================================
def test_main_sai_com_codigo_dois_e_marca_a_falha_de_banco(monkeypatch, capsys):
    def explode():
        raise servidor.ErroDePreparacaoDoBanco("Disco cheio.", "C:/dados/adri.db")

    subiu = []
    monkeypatch.setattr(servidor, 'preparar_banco', explode)
    monkeypatch.setattr(servidor.app, 'run', lambda **_: subiu.append(True))

    assert servidor.main() == 2
    assert subiu == [], "o Flask nao pode subir sobre um banco em duvida"

    saida = capsys.readouterr().err
    assert servidor.MARCADOR_FALHA_BANCO in saida
    assert "Disco cheio." in saida


# =============================================================================
# Banco vindo do caminho de emergencia
#
# `garantir_schema_fallback` monta o schema completo e nao grava revisao
# nenhuma. Para o Alembic, o resultado e um banco "legado" -- e tentar migrar
# dali faz a migration inicial rodar CREATE TABLE sobre tabelas que ja
# existem. Sem regularizacao, a inicializacao passaria a recusar o banco a
# partir da SEGUNDA execucao: o app abriria uma vez e nunca mais.
# =============================================================================
def test_banco_do_fallback_e_regularizado_no_boot(monkeypatch, tmp_path):
    caminho = tmp_path / "emergencia.db"
    _apontar_para(monkeypatch, caminho)
    monkeypatch.setattr(database, "DB_PATH", str(caminho))

    database.criar_tabela()
    with database.conectar() as conexao:
        conexao.execute(
            "INSERT INTO clientes (nome, cep, rua, bairro, cidade, entrega_retirada) "
            "VALUES ('Do fallback', '11000-000', 'Rua', 'Centro', 'Santos', 'Entrega')"
        )
    assert migrations_manager.estado_do_banco() == migrations_manager.ESTADO_LEGADO

    servidor.preparar_banco()

    assert migrations_manager.estado_do_banco() == migrations_manager.ESTADO_VERSIONADO
    assert migrations_manager.revisao_do_banco() == migrations_manager.revisao_alvo()
    assert migrations_manager.ha_migracoes_pendentes() is False

    with database.conectar() as conexao:
        assert conexao.execute("SELECT COUNT(*) FROM clientes").fetchone()[0] == 1


def test_regularizar_banco_legado_faz_backup_antes(monkeypatch, tmp_path):
    """Carimbar tambem mexe no banco. Se der errado, o operador precisa de
    para onde voltar."""
    caminho = tmp_path / "emergencia.db"
    _apontar_para(monkeypatch, caminho)
    monkeypatch.setattr(database, "DB_PATH", str(caminho))
    database.criar_tabela()
    with database.conectar() as conexao:
        conexao.execute(
            "INSERT INTO clientes (nome, cep, rua, bairro, cidade, entrega_retirada) "
            "VALUES ('Antes de carimbar', '11000-000', 'Rua', 'Centro', 'Santos', 'Entrega')"
        )

    servidor.preparar_banco()

    copias = backup.listar_copias(str(caminho))
    assert any(c["motivo"] == backup.MOTIVO_PRE_MIGRACAO for c in copias),         "nao guardou copia antes de regularizar o banco"


def test_segundo_boot_do_banco_regularizado_e_silencioso(monkeypatch, tmp_path):
    caminho = tmp_path / "emergencia.db"
    _apontar_para(monkeypatch, caminho)
    monkeypatch.setattr(database, "DB_PATH", str(caminho))
    database.criar_tabela()

    servidor.preparar_banco()
    revisao = migrations_manager.revisao_do_banco()
    servidor.preparar_banco()

    # Nada mudou: o banco ja estava na cabeca e nao ha o que regularizar.
    assert migrations_manager.revisao_do_banco() == revisao
