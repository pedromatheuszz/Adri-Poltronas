"""
A copia externa precisa abrir no dia em que o computador nao existe mais.

Ate a 1.5.2 a copia levada a `ADRI_BACKUP_EXTRA` era um duplicado da copia
local, cifrada com uma chave presa a conta do Windows. Ela existe para o
roubo, o disco morto e o ransomware -- e em todos eles a chave vai junto: o
pendrive guardava um arquivo que ninguem conseguia abrir.

Dois comportamentos sao provados aqui:

* com `ADRI_BACKUP_SENHA`, a copia externa e cifrada com a senha e restaura
  em "outro computador" (outra chave de conta), desde que a senha seja a
  mesma;
* a chave da conta nunca e sobrescrita -- se deixa de abrir, e posta de lado.
"""
import logging
import os
import sqlite3
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

import security  # noqa: E402
import segredos  # noqa: E402
from cryptography.fernet import Fernet  # noqa: E402
from erp.core import backup  # noqa: E402

SENHA = 'uma senha longa de recuperacao'


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


def _nomes(caminho):
    conexao = sqlite3.connect(caminho)
    try:
        return [linha[0] for linha in conexao.execute("SELECT nome FROM clientes ORDER BY id")]
    finally:
        conexao.close()


@pytest.fixture
def banco(tmp_path):
    (tmp_path / 'origem').mkdir()
    return _banco_com_dados(str(tmp_path / 'origem' / 'adri_poltronas.db'))


@pytest.fixture
def pendrive(tmp_path, monkeypatch):
    pasta = tmp_path / 'pendrive'
    monkeypatch.setenv(backup.VARIAVEL_DESTINO_EXTRA, str(pasta))
    return pasta


@pytest.fixture
def cofre_vazio(monkeypatch):
    """Nenhuma senha vinda de fora do teste."""
    monkeypatch.setattr(segredos, '_cache', {})
    monkeypatch.setattr(segredos, '_origem_env', set())
    monkeypatch.delenv(backup.VARIAVEL_SENHA_DAS_COPIAS, raising=False)


@pytest.fixture
def com_senha(cofre_vazio, monkeypatch):
    monkeypatch.setenv(backup.VARIAVEL_SENHA_DAS_COPIAS, SENHA)


def _copia_externa(pendrive):
    arquivos = sorted(pendrive.glob('adri_poltronas_diario_*.db'))
    assert len(arquivos) == 1, f'esperava uma copia externa, achei {arquivos}'
    return str(arquivos[0])


def _em_outro_computador(monkeypatch):
    """Troca a chave da conta: e o que acontece ao trocar de maquina."""
    monkeypatch.setattr(security, '_fernet_key_cache', Fernet.generate_key())


# =============================================================================
# Com senha: a copia externa e portatil
# =============================================================================
def test_copia_externa_com_senha_nao_depende_da_chave_da_conta(banco, pendrive, com_senha):
    backup.criar_backup(banco, backup.MOTIVO_DIARIO)
    externa = _copia_externa(pendrive)

    conteudo = open(externa, encoding='ascii').read()
    assert conteudo.startswith(security.MAGICO_BYTES_SENHA)
    assert backup._portatil(externa) is True
    # A chave da conta nao abre: a copia nao e um duplicado da local.
    assert security.decifrar_bytes(conteudo) is None
    assert b'SQLite format 3' not in conteudo.encode('ascii')


def test_copia_local_continua_presa_a_conta(banco, pendrive, com_senha):
    """A senha muda a copia que SAI; a que fica segue como era."""
    local = backup.criar_backup(banco, backup.MOTIVO_DIARIO)
    assert open(local, encoding='ascii').read().startswith(security.MAGICO_BYTES)
    assert backup._portatil(local) is False


def test_copia_portatil_restaura_em_outro_computador(banco, pendrive, com_senha,
                                                     tmp_path, monkeypatch):
    """O cenario que justifica tudo: maquina nova, mesma senha, arquivo do pendrive."""
    backup.criar_backup(banco, backup.MOTIVO_DIARIO)
    externa = _copia_externa(pendrive)

    _em_outro_computador(monkeypatch)
    (tmp_path / 'novo').mkdir()
    banco_novo = _banco_com_dados(str(tmp_path / 'novo' / 'adri_poltronas.db'), quantidade=1)

    ok, mensagem = backup.restaurar(banco_novo, externa)

    assert ok, mensagem
    assert _nomes(banco_novo) == ['Cliente 0', 'Cliente 1', 'Cliente 2']


def test_copia_local_nao_restaura_em_outro_computador(banco, pendrive, com_senha,
                                                      tmp_path, monkeypatch):
    """O contraste: e exatamente o que a copia externa fazia antes."""
    local = backup.criar_backup(banco, backup.MOTIVO_DIARIO)

    _em_outro_computador(monkeypatch)
    (tmp_path / 'novo').mkdir()
    banco_novo = _banco_com_dados(str(tmp_path / 'novo' / 'adri_poltronas.db'), quantidade=1)

    ok, mensagem = backup.restaurar(banco_novo, local)

    assert not ok
    assert 'outra conta do Windows' in mensagem
    assert _nomes(banco_novo) == ['Cliente 0']


def test_senha_errada_nao_abre_e_a_mensagem_aponta_a_senha(banco, pendrive, com_senha,
                                                          tmp_path, monkeypatch):
    backup.criar_backup(banco, backup.MOTIVO_DIARIO)
    externa = _copia_externa(pendrive)

    monkeypatch.setenv(backup.VARIAVEL_SENHA_DAS_COPIAS, 'outra senha, igualmente longa')
    (tmp_path / 'novo').mkdir()
    banco_novo = _banco_com_dados(str(tmp_path / 'novo' / 'adri_poltronas.db'), quantidade=1)

    ok, mensagem = backup.restaurar(banco_novo, externa)

    assert not ok
    assert backup.VARIAVEL_SENHA_DAS_COPIAS in mensagem
    assert _nomes(banco_novo) == ['Cliente 0'], 'o banco nao pode ser tocado'


def test_listagem_diz_qual_copia_e_portatil(banco, pendrive, com_senha, tmp_path):
    backup.criar_backup(banco, backup.MOTIVO_DIARIO)
    externa = _copia_externa(pendrive)

    # O operador copia o arquivo do pendrive para a pasta de backups da
    # instalacao nova; e ali que a tela de restauracao procura.
    (tmp_path / 'novo').mkdir()
    banco_novo = str(tmp_path / 'novo' / 'adri_poltronas.db')
    pasta = backup.pasta_de_backups(banco_novo)
    os.makedirs(pasta)
    destino = os.path.join(pasta, os.path.basename(externa))
    with open(externa, 'rb') as origem, open(destino, 'wb') as copia:
        copia.write(origem.read())

    copias = backup.listar_copias(banco_novo)
    assert [c['portatil'] for c in copias] == [True]
    assert backup.caminho_da_copia(banco_novo, copias[0]['arquivo']) == destino


def test_sal_novo_a_cada_copia():
    """Duas copias do mesmo conteudo com a mesma senha nao podem ser iguais:
    sal repetido deixaria comparar pendrives para saber se o banco mudou."""
    uma = security.cifrar_bytes_com_senha(b'conteudo', SENHA)
    outra = security.cifrar_bytes_com_senha(b'conteudo', SENHA)
    assert uma != outra
    assert security.decifrar_bytes_com_senha(uma, SENHA) == b'conteudo'
    assert security.decifrar_bytes_com_senha(outra, SENHA) == b'conteudo'


def test_copia_portatil_adulterada_nao_abre():
    cifrado = security.cifrar_bytes_com_senha(b'conteudo', SENHA)
    adulterado = cifrado[:-6] + ('A' if cifrado[-6] != 'A' else 'B') + cifrado[-5:]
    assert security.decifrar_bytes_com_senha(adulterado, SENHA) is None


# =============================================================================
# Sem senha: nada quebra, e o log diz o que a copia nao faz
# =============================================================================
def test_sem_senha_a_copia_externa_e_o_duplicado_de_antes(banco, pendrive, cofre_vazio, caplog):
    with caplog.at_level(logging.WARNING, logger='adri.backup'):
        local = backup.criar_backup(banco, backup.MOTIVO_DIARIO)
    externa = _copia_externa(pendrive)

    assert open(externa, 'rb').read() == open(local, 'rb').read()
    aviso = ' '.join(r.getMessage() for r in caplog.records)
    assert backup.VARIAVEL_SENHA_DAS_COPIAS in aviso
    assert 'so abre NESTA conta' in aviso


def test_senha_curta_conta_como_ausente(banco, pendrive, cofre_vazio, monkeypatch):
    """Cifrar com 'abc123' daria impressao de protecao num arquivo que se
    abre por tentativa."""
    monkeypatch.setenv(backup.VARIAVEL_SENHA_DAS_COPIAS, 'curta')
    assert backup.senha_das_copias() == ''

    backup.criar_backup(banco, backup.MOTIVO_DIARIO)
    assert backup._portatil(_copia_externa(pendrive)) is False


def test_pendrive_ausente_nao_derruba_a_copia_local(banco, com_senha, tmp_path, monkeypatch):
    arquivo_no_lugar_da_pasta = tmp_path / 'nao-e-pasta'
    arquivo_no_lugar_da_pasta.write_text('x')
    monkeypatch.setenv(backup.VARIAVEL_DESTINO_EXTRA, str(arquivo_no_lugar_da_pasta))

    local = backup.criar_backup(banco, backup.MOTIVO_DIARIO)

    assert local and os.path.exists(local)


def test_senha_das_copias_e_migrada_para_o_cofre():
    """Senha em texto no `.env` e o banco inteiro do pendrive ao alcance de
    quem ler o arquivo."""
    assert backup.VARIAVEL_SENHA_DAS_COPIAS in segredos.CHAVES_MIGRAVEIS
    assert backup.VARIAVEL_SENHA_DAS_COPIAS in segredos.CHAVES_PROTEGIDAS


# =============================================================================
# A chave da conta nunca e sobrescrita
# =============================================================================
class _DpapiQueNaoAbre:
    """A conta que cifrou nao e mais a que esta pedindo para decifrar."""

    @staticmethod
    def CryptUnprotectData(*_args):
        raise OSError('Chave nao valida para uso no estado especificado.')

    @staticmethod
    def CryptProtectData(dados, *_args):
        return b'protegido:' + dados


@pytest.fixture
def chave_ilegivel(tmp_path, monkeypatch):
    monkeypatch.setenv('APPDATA', str(tmp_path))
    monkeypatch.delenv('FERNET_KEY', raising=False)
    monkeypatch.setattr(security, '_fernet_key_cache', None)
    monkeypatch.setattr(security, '_importar_win32crypt', lambda: _DpapiQueNaoAbre)

    pasta = tmp_path / 'AdriPoltronas'
    pasta.mkdir()
    arquivo = pasta / '.fernet_key'
    arquivo.write_text('chave-antiga-que-esta-conta-nao-abre')
    return arquivo


def test_chave_ilegivel_e_preservada_e_nao_sobrescrita(chave_ilegivel):
    nova = security._obter_chave_fernet()

    postas_de_lado = list(chave_ilegivel.parent.glob('.fernet_key.ilegivel-*'))
    assert len(postas_de_lado) == 1
    assert postas_de_lado[0].read_text() == 'chave-antiga-que-esta-conta-nao-abre'
    # A nova existe e e utilizavel; a antiga nao foi perdida para isso.
    assert chave_ilegivel.exists()
    Fernet(nova)


def test_sem_conseguir_preservar_nenhuma_chave_nova_e_gravada(chave_ilegivel, monkeypatch):
    monkeypatch.setattr(security, '_por_chave_ilegivel_de_lado', lambda _caminho: None)

    with pytest.raises(RuntimeError):
        security._obter_chave_fernet()

    assert chave_ilegivel.read_text() == 'chave-antiga-que-esta-conta-nao-abre'
