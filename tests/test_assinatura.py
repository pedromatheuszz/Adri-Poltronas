"""
Assinatura de codigo: o comando existe, ou as instrucoes existem -- nunca os dois pela metade.

O SmartScreen avisa sobre o instalador nao assinado, e o SECURITY.md
registrava isso como limitacao. `python build.py assinar` e o caminho para
mudar; estes testes seguram as bordas que nao precisam de certificado
real para serem verificaveis: o thumbprint validado, a linha de comando
montada, os alvos descobertos e as recusas com mensagem que ensina.

Nao ha teste que assine de verdade: exigiria certificado e signtool na
maquina, e a suite precisa passar em qualquer computador. O que vale
conferir sem isso e tudo o que vem ANTES do signtool -- que e onde um
comando dessos costuma falhar de forma confusa.
"""
import os
import sys

import pytest

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, RAIZ)
sys.path.insert(0, os.path.join(RAIZ, 'backend'))

import build  # noqa: E402


# =============================================================================
# O thumbprint
# =============================================================================
def test_thumbprint_valido_e_normalizado():
    assert build.validar_thumbprint(
        'ab cd ef 01 23 45 67 89 ab cd ef 01 23 45 67 89 ab cd ef 01'
    ) == 'ABCDEF0123456789ABCDEF0123456789ABCDEF01'
    assert build.validar_thumbprint('abc') is None


@pytest.mark.parametrize('errado', [
    '', 'curto', 'z' * 40, '1' * 39, 'g' * 40, None,
])
def test_thumbprint_que_nao_e_sha1_e_recusado(errado):
    assert build.validar_thumbprint(errado) is None


# =============================================================================
# A linha de comando
# =============================================================================
def test_argumentos_usam_o_certificado_do_repositorio_quando_ha():
    args = build.argumentos_de_assinatura(
        'Setup.exe', 'AABB', None, 'http://carimbo')

    assert args[:6] == ['sign', '/fd', 'SHA256', '/td', 'SHA256', '/tr']
    assert '/sha1' in args and 'AABB' in args
    # O executavel e o ultimo: e o alvo, e nao uma opcao.
    assert args[-1] == 'Setup.exe'
    # /p so entra com pfx; thumbprint nao expoe senha nenhuma.
    assert '/p' not in args and '/f' not in args


def test_argumentos_usam_o_pfx_quando_nao_ha_thumbprint():
    args = build.argumentos_de_assinatura(
        'Setup.exe', None, 'certificado.pfx', 'http://carimbo')

    assert '/f' in args and 'certificado.pfx' in args
    assert '/sha1' not in args


def test_o_carimbo_rfc3161_vem_sempre_na_assinatura():
    """Sem carimbo, a assinatura morre com o certificado. Ele nao e opcional."""
    args = build.argumentos_de_assinatura('Setup.exe', 'AA', None, 'http://carimbo')
    assert '/tr' in args and 'http://carimbo' in args
    assert '/td' in args


# =============================================================================
# Os alvos
# =============================================================================
def test_procura_instalador_e_backend_sem_ignorar_nenhum(tmp_path, monkeypatch):
    instalador = tmp_path / 'dist-instalador'
    instalador.mkdir()
    (instalador / 'AdriPoltronasSetup-1.5.2-beta.exe').write_bytes(b'x')
    (instalador / 'bloco-de-notas.tmp').write_bytes(b'x')

    backend = tmp_path / 'dist' / 'AdriPoltronasBackend'
    backend.mkdir(parents=True)
    (backend / 'AdriPoltronasBackend.exe').write_bytes(b'x')

    monkeypatch.setattr(build, 'INSTALADOR_DIR', instalador)
    monkeypatch.setattr(build, 'DIST_DIR', tmp_path / 'dist')

    alvos = build.executaveis_para_assinar()

    assert [alvo.name for alvo in alvos] == [
        'AdriPoltronasSetup-1.5.2-beta.exe', 'AdriPoltronasBackend.exe']
    # So .exe; o arquivo de outra extensao na mesma pasta nao entra.


def test_sem_build_o_comando_diz_o_que_falta(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(build, 'INSTALADOR_DIR', tmp_path / 'vazio')
    monkeypatch.setattr(build, 'DIST_DIR', tmp_path / 'vazio2')

    assert build.assinar() is False
    saida = capsys.readouterr().out
    assert 'installer' in saida, "precisa dizer qual comando gera os alvos"


def test_sem_credencial_o_comando_ensina_as_duas_formas(monkeypatch, capsys):
    for variavel in ('ADRI_CERT_THUMBPRINT', 'ADRI_CERT_ARQUIVO', 'ADRI_CERT_SENHA'):
        monkeypatch.delenv(variavel, raising=False)
    monkeypatch.setattr(build, 'executaveis_para_assinar',
                        lambda: ['ficticio.exe'])
    # Sem signtool a chamada nem comeca: a recusa aqui e de credencial.
    monkeypatch.setattr(build, 'localizar_signtool', lambda: None)

    assert build.assinar() is False
    saida = capsys.readouterr().out
    assert 'ADRI_CERT_THUMBPRINT' in saida
    assert 'ADRI_CERT_ARQUIVO' in saida


def test_thumbprint_malformado_e_recusado_antes_do_signtool(monkeypatch, capsys):
    monkeypatch.setenv('ADRI_CERT_THUMBPRINT', '1234')
    monkeypatch.delenv('ADRI_CERT_ARQUIVO', raising=False)
    monkeypatch.delenv('ADRI_CERT_SENHA', raising=False)
    monkeypatch.setattr(build, 'executaveis_para_assinar',
                        lambda: ['ficticio.exe'])
    monkeypatch.setattr(build, 'localizar_signtool', lambda: None)

    assert build.assinar() is False
    assert 'SHA-1' in capsys.readouterr().out
