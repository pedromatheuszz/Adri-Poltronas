"""
Testes do modulo `security`.

Cobrem a camada de criptografia, hashing, CSRF, sessoes, sanitizacao, upload e
protecao contra forca bruta. Antes destes testes o modulo estava em 40% de
cobertura -- justamente o codigo que decide se um segredo vaza ou nao.
"""
import os
import sys
import time

import pytest

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
# CSRF
# -----------------------------------------------------------------------------
def test_csrf_token_valido_e_aceito():
    token = security.gerar_csrf_token("usuario-1")
    assert security.validar_csrf_token(token, "usuario-1")


def test_csrf_token_de_outro_usuario_e_recusado():
    token = security.gerar_csrf_token("usuario-1")
    assert not security.validar_csrf_token(token, "usuario-2")


def test_csrf_token_desconhecido_e_recusado():
    assert not security.validar_csrf_token("token-que-nunca-existiu")


def test_csrf_tokens_sao_unicos():
    assert security.gerar_csrf_token("u") != security.gerar_csrf_token("u")


# -----------------------------------------------------------------------------
# Sessoes
# -----------------------------------------------------------------------------
def test_sessao_criada_e_valida():
    sessao_id = security.criar_sessao_segura("conta@exemplo.com", "token-oauth")
    dados = security.validar_sessao_segura(sessao_id)
    assert dados is not None
    security.destruir_sessao_segura(sessao_id)


def test_sessao_destruida_deixa_de_valer():
    sessao_id = security.criar_sessao_segura("conta@exemplo.com", "token")
    security.destruir_sessao_segura(sessao_id)
    assert security.validar_sessao_segura(sessao_id) is None


def test_sessao_inexistente_e_invalida():
    assert security.validar_sessao_segura("id-que-nao-existe") is None


def test_sessao_expirada_e_recusada(monkeypatch):
    sessao_id = security.criar_sessao_segura("conta@exemplo.com", "token")
    # O relogio real precisa ser capturado ANTES da substituicao, senao a
    # lambda chama a si mesma e estoura a pilha.
    agora_real = time.time()
    monkeypatch.setattr(security.time, 'time',
                        lambda: agora_real + security._SESSAO_TIMEOUT + 60)
    assert security.validar_sessao_segura(sessao_id) is None


def test_hash_de_ip_e_estavel_e_nao_reversivel():
    assert security._hash_ip("192.168.0.1") == security._hash_ip("192.168.0.1")
    assert security._hash_ip("192.168.0.1") != security._hash_ip("192.168.0.2")
    assert "192.168.0.1" not in security._hash_ip("192.168.0.1")


# -----------------------------------------------------------------------------
# Sanitizacao
# -----------------------------------------------------------------------------
@pytest.mark.parametrize("entrada,proibido", [
    ("<script>alert(1)</script>ola", "<script>"),
    ('<div onclick="mal()">x</div>', "onclick="),
    ("javascript:alert(1)", "javascript:"),
    ("data:text/html;base64,AAAA", "data:"),
])
def test_sanitizar_texto_remove_vetores(entrada, proibido):
    assert proibido not in security.sanitizar_texto(entrada)


def test_sanitizar_texto_respeita_tamanho_maximo():
    assert len(security.sanitizar_texto("a" * 5000, max_len=100)) <= 100


def test_sanitizar_texto_com_nao_string_devolve_vazio():
    assert security.sanitizar_texto(None) == ""
    assert security.sanitizar_texto(123) == ""


def test_sanitizar_html_escapa_todos_os_metacaracteres():
    escapado = security.sanitizar_html("""<a href="x">O'Brien & Cia</a>""")
    for bruto in ('<', '>', '"', "'"):
        assert bruto not in escapado
    assert "&amp;" in escapado


def test_sanitizar_html_com_nao_string_devolve_vazio():
    assert security.sanitizar_html(None) == ""


def test_validar_sql_safe_aceita_consulta_parametrizada():
    assert security.validar_sql_safe("SELECT * FROM clientes WHERE id=?", (1,))


def test_validar_sql_safe_recusa_concatenacao_suspeita():
    assert not security.validar_sql_safe("SELECT * FROM clientes WHERE nome='' OR 1=1--")


def test_validar_sql_safe_e_deliberadamente_conservador_sem_params():
    """
    Sem parametros a heuristica marca qualquer consulta que contenha palavras
    de SQL -- inclusive 'SELECT 1'. E um detector grosseiro, util so como
    alarme para concatenacao; nenhum caminho de producao depende dele (todas
    as consultas do app usam placeholders).
    """
    assert not security.validar_sql_safe("SELECT 1")
    assert security.validar_sql_safe("SELECT 1", (1,))


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
# Forca bruta
# -----------------------------------------------------------------------------
def test_ip_limpo_nao_esta_bloqueado():
    assert not security.esta_bloqueado_bruteforce("10.0.0.99")


def test_ip_e_bloqueado_apos_o_limite_de_tentativas():
    ip = "10.0.0.100"
    for _ in range(security._BRUTE_FORCE_MAX_TENTATIVAS):
        security.registrar_tentativa_login(ip, sucesso=False)
    assert security.esta_bloqueado_bruteforce(ip)


def test_login_bem_sucedido_limpa_as_tentativas():
    ip = "10.0.0.101"
    for _ in range(security._BRUTE_FORCE_MAX_TENTATIVAS):
        security.registrar_tentativa_login(ip, sucesso=False)
    security.registrar_tentativa_login(ip, sucesso=True)
    assert not security.esta_bloqueado_bruteforce(ip)


def test_abaixo_do_limite_nao_bloqueia():
    ip = "10.0.0.102"
    for _ in range(security._BRUTE_FORCE_MAX_TENTATIVAS - 1):
        security.registrar_tentativa_login(ip, sucesso=False)
    assert not security.esta_bloqueado_bruteforce(ip)


# -----------------------------------------------------------------------------
# Assinatura de requisicao
# -----------------------------------------------------------------------------
def test_assinatura_confere_com_o_mesmo_segredo():
    dados = {"valor": 100, "id": 7}
    assinatura = security.assinar_request(dados, "segredo")
    assert security.verificar_assinatura(dados, "segredo", assinatura)


def test_assinatura_nao_confere_com_outro_segredo():
    dados = {"valor": 100}
    assinatura = security.assinar_request(dados, "segredo")
    assert not security.verificar_assinatura(dados, "outro-segredo", assinatura)


def test_assinatura_detecta_alteracao_do_payload():
    assinatura = security.assinar_request({"valor": 100}, "segredo")
    assert not security.verificar_assinatura({"valor": 999}, "segredo", assinatura)


def test_assinatura_independe_da_ordem_das_chaves():
    a = security.assinar_request({"a": 1, "b": 2}, "s")
    b = security.assinar_request({"b": 2, "a": 1}, "s")
    assert a == b


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
