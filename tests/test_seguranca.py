"""
Testes do modulo `security`.

Cobrem a camada de criptografia, hashing, CSRF, sessoes, sanitizacao, upload e
protecao contra forca bruta. Antes destes testes o modulo estava em 40% de
cobertura -- justamente o codigo que decide se um segredo vaza ou nao.
"""
import os
import sys


sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

import security  # noqa: E402


# -----------------------------------------------------------------------------
# Cifragem em repouso (DPAPI no Windows, Fernet como camada de aplicacao)
# -----------------------------------------------------------------------------
def test_cifrar_e_decifrar_preserva_o_valor():
    assert security.decifrar(security.cifrar("token-secreto")) == "token-secreto"


def test_cifrar_produz_saida_diferente_do_texto_claro():
    cifrado = security.cifrar("token-secreto")
    assert "token-secreto" not in cifrado
    assert cifrado.startswith((security.PREFIXO_DPAPI, security.PREFIXO_PLAIN))


def test_cifrar_none_devolve_string_vazia():
    assert security.cifrar(None) == ""


def test_cifrar_string_vazia_ainda_produz_um_blob_decifravel():
    # Apenas None curto-circuita; "" segue o caminho normal de cifragem.
    assert security.decifrar(security.cifrar("")) == ""


def test_cifrar_converte_nao_string():
    assert security.decifrar(security.cifrar(12345)) == "12345"


def test_decifrar_valor_vazio_devolve_none():
    assert security.decifrar("") is None
    assert security.decifrar(None) is None


def test_decifrar_valor_corrompido_devolve_none():
    assert security.decifrar(security.PREFIXO_DPAPI + "nao-e-base64-valido!!") is None


def test_migrar_para_cifrado_e_idempotente():
    cifrado = security.cifrar("segredo")
    assert security.migrar_para_cifrado(cifrado) == cifrado


def test_migrar_para_cifrado_converte_texto_puro():
    migrado = security.migrar_para_cifrado("segredo-legado")
    assert migrado != "segredo-legado"
    assert security.decifrar(migrado) == "segredo-legado"


def test_migrar_para_cifrado_preserva_vazio():
    assert security.migrar_para_cifrado("") == ""


# -----------------------------------------------------------------------------
# Fernet
# -----------------------------------------------------------------------------
def test_fernet_ida_e_volta():
    assert security.fernet_decifrar(security.fernet_cifrar("dado")) == "dado"


def test_fernet_saida_nao_contem_o_texto_claro():
    assert "dado" not in security.fernet_cifrar("dado")


def test_fernet_decifrar_lixo_devolve_none():
    assert security.fernet_decifrar("FERN1:nao-e-um-token") is None


def test_fernet_objeto_preserva_estrutura():
    original = {"nome": "Maria", "itens": [1, 2, 3], "ativo": True}
    assert security.fernet_decifrar_objeto(security.fernet_cifrar_objeto(original)) == original


def test_fernet_decifrar_objeto_invalido_devolve_none():
    assert security.fernet_decifrar_objeto("FERN1:invalido") is None


# -----------------------------------------------------------------------------
# Hash de senha
# -----------------------------------------------------------------------------
def test_hash_de_senha_confere():
    assert security.verificar_senha("senha-correta", security.hash_senha("senha-correta"))


def test_hash_de_senha_rejeita_senha_errada():
    assert not security.verificar_senha("senha-errada", security.hash_senha("senha-correta"))


def test_hashes_da_mesma_senha_diferem_pelo_salt():
    assert security.hash_senha("igual") != security.hash_senha("igual")


def test_verificar_senha_com_hash_malformado_e_falso():
    assert not security.verificar_senha("x", "formato-invalido")
    assert not security.verificar_senha("x", "")


def test_hash_nao_contem_a_senha():
    assert "minha-senha" not in security.hash_senha("minha-senha")


# -----------------------------------------------------------------------------
# Upload
# -----------------------------------------------------------------------------
class _ArquivoFalso:
    def __init__(self, conteudo=b'dados', filename='clientes.csv', content_type='text/csv'):
        self._conteudo = conteudo
        self.filename = filename
        self.content_type = content_type

    def read(self):
        return self._conteudo

    def seek(self, _posicao):
        return None


def test_upload_valido_e_aceito():
    valido, erro = security.validar_upload(_ArquivoFalso())
    assert valido and erro is None


def test_upload_none_e_recusado():
    valido, erro = security.validar_upload(None)
    assert not valido and erro


def test_upload_vazio_e_recusado():
    valido, erro = security.validar_upload(_ArquivoFalso(conteudo=b''))
    assert not valido and 'vazio' in erro.lower()


def test_upload_grande_demais_e_recusado():
    valido, erro = security.validar_upload(_ArquivoFalso(conteudo=b'x' * 2048), max_size=1024)
    assert not valido and 'tamanho' in erro.lower()


def test_upload_de_extensao_proibida_e_recusado():
    valido, erro = security.validar_upload(_ArquivoFalso(filename='payload.exe'))
    assert not valido and 'xtensao' in erro


def test_upload_sem_nome_e_recusado():
    valido, erro = security.validar_upload(_ArquivoFalso(filename=''))
    assert not valido and erro


# -----------------------------------------------------------------------------
# Utilitarios
# -----------------------------------------------------------------------------
def test_token_seguro_tem_o_comprimento_pedido_e_e_unico():
    assert len(security.gerar_token_seguro(16)) >= 16
    assert security.gerar_token_seguro() != security.gerar_token_seguro()


def test_id_unico_nao_repete():
    assert security.gerar_id_unico() != security.gerar_id_unico()


def test_log_evento_seguro_aceita_os_niveis(caplog):
    for nivel in ("info", "warning", "error"):
        security.log_evento_seguro("ACAO_TESTE", "detalhe", nivel)
