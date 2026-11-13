"""
A resposta da API central de licencas e assinada, e o aplicativo so acredita
no que esta assinado.

Antes havia duas portas, ambas sem esforco: apontar `ADRI_LICENCA_API_URL`
para um servidor que respondesse `"paid"`, ou editar as colunas
`licenca_remota_*` no SQLite. Os testes abaixo exercitam as duas pontas de
verdade -- a funcao que o servico usa para assinar e a que o aplicativo usa
para conferir -- com um par de chaves gerado na hora.
"""
import base64
import importlib.util
import json
import os
import sys
import types
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(RAIZ, 'backend'))

import database  # noqa: E402
import licenca_remota  # noqa: E402

INSTALACAO = 'a' * 64
OUTRA_INSTALACAO = 'b' * 64


def _carregar(nome, arquivo):
    if nome in sys.modules:
        return sys.modules[nome]
    spec = importlib.util.spec_from_file_location(
        nome, os.path.join(RAIZ, 'licensing-service', arquivo))
    modulo = importlib.util.module_from_spec(spec)
    sys.modules[nome] = modulo
    spec.loader.exec_module(modulo)
    return modulo


# O ambiente do ERP usa SQLite e pode nao ter o psycopg; o servico so precisa
# dele para falar com o banco, que estes testes nao tocam.
if 'psycopg' not in sys.modules:
    _psycopg = types.ModuleType('psycopg')
    _rows = types.ModuleType('psycopg.rows')
    _rows.dict_row = MagicMock()
    _psycopg.rows = _rows
    _psycopg.connect = MagicMock()
    sys.modules['psycopg'] = _psycopg
    sys.modules['psycopg.rows'] = _rows

servico = _carregar('licensing_service_app', 'app.py')
gerador = _carregar('licensing_service_gerar_chave', 'gerar_chave_de_assinatura.py')


@pytest.fixture
def par_de_chaves(monkeypatch):
    """Servico com a chave privada, aplicativo com a publica."""
    privada, publica = gerador.gerar_par()
    monkeypatch.setenv('LICENSE_SIGNING_KEY', privada)
    monkeypatch.setattr(servico, '_chave_de_assinatura', None)
    monkeypatch.setattr(servico, '_chave_de_assinatura_lida', False)
    monkeypatch.setattr(licenca_remota, 'CHAVE_PUBLICA_DA_CENTRAL', publica)
    return privada, publica


def _registro(license_id='conta-1', estado='paid', expira_em=''):
    return {'license_id': license_id, 'estado': estado, 'expira_em': expira_em}


def _emitir(estado='paid', license_id='conta-1', instalacao=INSTALACAO, expira_em=''):
    return servico._assinar_registro(_registro(license_id, estado, expira_em), instalacao)


def _em_30_dias():
    return (datetime.now(timezone.utc) + timedelta(days=30)).strftime('%Y-%m-%dT%H:%M:%SZ')


# =============================================================================
# A prova: o que o aplicativo aceita e o que recusa
# =============================================================================
def test_prova_emitida_pelo_servico_e_aceita_pelo_aplicativo(par_de_chaves):
    dados = licenca_remota.verificar_prova(_emitir('paid'), 'conta-1', INSTALACAO)

    assert dados['estado'] == 'paid'
    assert dados['license_id'] == 'conta-1'
    assert dados['installation_id'] == INSTALACAO
    assert dados['emitida_em']


def test_servidor_falso_nao_consegue_emitir(par_de_chaves, monkeypatch):
    """Quem redireciona a URL controla a resposta, mas nao tem a chave privada."""
    prova_verdadeira = _emitir('paid')

    privada_do_impostor, _ = gerador.gerar_par()
    monkeypatch.setenv('LICENSE_SIGNING_KEY', privada_do_impostor)
    monkeypatch.setattr(servico, '_chave_de_assinatura_lida', False)
    prova_do_impostor = _emitir('paid')

    assert licenca_remota.verificar_prova(prova_verdadeira, 'conta-1', INSTALACAO)
    assert licenca_remota.verificar_prova(prova_do_impostor, 'conta-1', INSTALACAO) is None


def test_trocar_o_estado_dentro_da_prova_invalida_a_assinatura(par_de_chaves):
    corpo, assinatura = _emitir('suspended').split('.')
    dados = json.loads(base64.urlsafe_b64decode(corpo + '=' * (-len(corpo) % 4)))
    dados['estado'] = 'paid'
    forjado = base64.urlsafe_b64encode(
        json.dumps(dados, separators=(',', ':')).encode()).rstrip(b'=').decode()

    assert licenca_remota.verificar_prova(forjado + '.' + assinatura, 'conta-1', INSTALACAO) is None


def test_prova_de_outra_conta_ou_de_outro_computador_nao_serve(par_de_chaves):
    """Copiar a prova "paga" do banco de um cliente para o de outro."""
    prova = _emitir('paid')

    assert licenca_remota.verificar_prova(prova, 'conta-2', INSTALACAO) is None
    assert licenca_remota.verificar_prova(prova, 'conta-1', OUTRA_INSTALACAO) is None


@pytest.mark.parametrize('lixo', [None, '', 'sem-ponto', 'a.b.c', '.', 'x.', '.y', 12, 'a' * 5000])
def test_prova_malformada_e_recusada_sem_estourar(par_de_chaves, lixo):
    assert licenca_remota.verificar_prova(lixo, 'conta-1', INSTALACAO) is None


def test_sem_chave_publica_a_exigencia_fica_desligada(monkeypatch):
    """Exigir assinatura antes de o servico assinar trancaria todos os
    clientes. A ativacao e deliberada: colar a chave publica no codigo."""
    monkeypatch.setattr(licenca_remota, 'CHAVE_PUBLICA_DA_CENTRAL', '')
    assert licenca_remota.assinatura_exigida() is False


def test_chave_publica_nao_vem_do_ambiente(par_de_chaves, monkeypatch):
    """Lida do `.env`, quem redireciona a URL trocaria a chave no mesmo arquivo."""
    _, publica_do_impostor = gerador.gerar_par()
    monkeypatch.setenv('CHAVE_PUBLICA_DA_CENTRAL', publica_do_impostor)
    monkeypatch.setenv('ADRI_LICENCA_CHAVE_PUBLICA', publica_do_impostor)

    assert licenca_remota.verificar_prova(_emitir('paid'), 'conta-1', INSTALACAO)


# =============================================================================
# O servico
# =============================================================================
def test_sem_chave_privada_o_servico_responde_sem_prova(monkeypatch):
    """E o que permite publicar o servico antes de os aplicativos exigirem."""
    monkeypatch.delenv('LICENSE_SIGNING_KEY', raising=False)
    monkeypatch.setattr(servico, '_chave_de_assinatura_lida', False)

    assert servico._assinar_registro(_registro(), INSTALACAO) == ''


@pytest.mark.parametrize('chave', ['nao-e-base64!', base64.b64encode(b'curta').decode()])
def test_chave_privada_malformada_impede_o_servico_de_subir(monkeypatch, chave):
    monkeypatch.setenv('LICENSE_SIGNING_KEY', chave)
    monkeypatch.setattr(servico, '_chave_de_assinatura_lida', False)

    with pytest.raises(RuntimeError):
        servico._carregar_chave_de_assinatura()


def test_a_prova_nao_carrega_a_chave_privada(par_de_chaves):
    privada, _ = par_de_chaves
    assert privada not in _emitir('paid')


# =============================================================================
# O aplicativo: sincronizacao e cache
# =============================================================================
@pytest.fixture
def conta(par_de_chaves, monkeypatch, tmp_path):
    banco = str(tmp_path / 'licenca.db')
    monkeypatch.setattr(database, 'DB_PATH', banco)
    database.criar_tabela()
    monkeypatch.setattr(licenca_remota, 'identidade_instalacao', lambda: INSTALACAO)

    user_id = database.criar_usuario('operador', 'senha-de-teste-longa', 'usuario', 'op@exemplo.local')
    license_id = database.obter_identidade_licenca_remota(user_id)['licenca_remota_id']
    return {'id': user_id, 'license_id': license_id}


def _central_responde(monkeypatch, resposta):
    monkeypatch.setattr(licenca_remota, '_requisicao', lambda *_a, **_k: resposta)


def _resposta_assinada(conta, estado, expira_em=''):
    registro = _registro(conta['license_id'], estado, expira_em)
    return {**registro, 'prova': servico._assinar_registro(registro, INSTALACAO)}


def _editar_cache(conta, **colunas):
    atribuicoes = ', '.join(f'{nome} = ?' for nome in colunas)
    with database.conectar() as conexao:
        conexao.execute(f'UPDATE usuarios SET {atribuicoes} WHERE id = ?',  # noqa: S608 - nomes fixos do proprio teste
                        (*colunas.values(), conta['id']))


def test_resposta_sem_assinatura_nao_libera_nem_e_gravada(conta, monkeypatch):
    """O servidor falso da URL redirecionada: responde "paid", sem prova."""
    _central_responde(monkeypatch, {'license_id': conta['license_id'], 'estado': 'paid'})

    assert licenca_remota.sincronizar_usuario(conta['id']) is None
    assert licenca_remota.situacao_em_cache(conta['id']) is None
    assert licenca_remota.cache_precisa_sincronizar(conta['id']) is True


def test_resposta_assinada_libera(conta, monkeypatch):
    _central_responde(monkeypatch, _resposta_assinada(conta, 'paid'))

    assert licenca_remota.sincronizar_usuario(conta['id'])['estado'] == 'paga'
    assert licenca_remota.situacao_em_cache(conta['id'])['estado'] == 'paga'
    assert licenca_remota.cache_precisa_sincronizar(conta['id']) is False


def test_vale_o_estado_assinado_e_nao_o_campo_solto(conta, monkeypatch):
    """Prova diz "suspended"; o JSON em volta dela diz "paid"."""
    resposta = _resposta_assinada(conta, 'suspended')
    resposta['estado'] = 'paid'
    _central_responde(monkeypatch, resposta)

    assert licenca_remota.sincronizar_usuario(conta['id'])['estado'] == 'expirada'


def test_editar_o_cache_no_sqlite_nao_libera(conta):
    """O contorno de uma linha de SQL que motivou a assinatura."""
    _editar_cache(conta, licenca_remota_estado='paid',
                  licenca_remota_offline_ate='2999-01-01T00:00:00')

    assert licenca_remota.situacao_em_cache(conta['id']) is None
    assert licenca_remota.cache_precisa_sincronizar(conta['id']) is True


def test_editar_as_colunas_nao_muda_o_que_a_prova_diz(conta, monkeypatch):
    _central_responde(monkeypatch, _resposta_assinada(conta, 'trial', _em_30_dias()))
    licenca_remota.sincronizar_usuario(conta['id'])

    _editar_cache(conta, licenca_remota_estado='paid',
                  licenca_remota_expira_em='2999-01-01T00:00:00',
                  licenca_remota_offline_ate='2999-01-01T00:00:00')

    situacao = licenca_remota.situacao_em_cache(conta['id'])
    assert situacao['estado'] == 'teste'
    assert situacao['dias_restantes'] <= 30


def test_prova_velha_obriga_a_falar_com_a_central(conta, monkeypatch):
    """
    A janela offline conta da emissao ASSINADA. Uma resposta "paga" guardada
    de antes de uma suspensao deixa de valer 72 horas depois de emitida, e
    esticar `offline_ate` no banco nao muda isso.
    """
    ha_73_horas = datetime.now(timezone.utc) - timedelta(hours=73)
    monkeypatch.setattr(servico, '_now', lambda: ha_73_horas.replace(microsecond=0))
    _central_responde(monkeypatch, _resposta_assinada(conta, 'paid'))
    licenca_remota.sincronizar_usuario(conta['id'])

    _editar_cache(conta, licenca_remota_offline_ate='2999-01-01T00:00:00')

    assert licenca_remota.cache_precisa_sincronizar(conta['id']) is True
    assert licenca_remota.situacao_em_cache(conta['id'])['estado'] == 'expirada'


def test_recusa_da_central_e_lembrada_sem_prova(conta, monkeypatch):
    """O cache sem assinatura ainda serve para NEGAR: evita repetir a consulta
    a cada requisicao logo depois de a central recusar a conta."""
    _central_responde(monkeypatch, _resposta_assinada(conta, 'paid'))
    licenca_remota.sincronizar_usuario(conta['id'])

    database.invalidar_licenca_remota_cache(conta['id'])

    assert licenca_remota.situacao_em_cache(conta['id'])['estado'] == 'expirada'
    assert licenca_remota.cache_precisa_sincronizar(conta['id']) is False


def test_banco_copiado_para_outro_computador_perde_a_liberacao(conta, monkeypatch):
    _central_responde(monkeypatch, _resposta_assinada(conta, 'paid'))
    licenca_remota.sincronizar_usuario(conta['id'])

    monkeypatch.setattr(licenca_remota, 'identidade_instalacao', lambda: OUTRA_INSTALACAO)

    assert licenca_remota.situacao_em_cache(conta['id']) is None
    assert licenca_remota.cache_precisa_sincronizar(conta['id']) is True
