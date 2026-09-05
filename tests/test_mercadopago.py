"""
Cliente do Mercado Pago -- a cobranca da licenca do proprio aplicativo.

O duplo de `urlopen` segue o mesmo desenho de test_integracoes.py: nenhuma
requisicao sai da maquina, e o que se exercita e a traducao entre o formato do
Mercado Pago e o que o resto do app espera.

O ponto sensivel testado aqui e o que decide se a licenca libera. "Pago" nao
pode ser generoso: `authorized` e cartao autorizado e NAO capturado -- dinheiro
reservado, nao recebido --, e liberar ali entregaria o produto por uma
transacao que ainda pode nao se concretizar.
"""
import io
import json
import logging
import os
import sys
import urllib.error

import pytest

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(RAIZ, 'backend'))

import mercadopago  # noqa: E402


class _RespostaFalsa:
    def __init__(self, corpo, status=200):
        self._corpo = corpo if isinstance(corpo, bytes) else json.dumps(corpo).encode()
        self.status = status

    def read(self):
        return self._corpo

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


def _erro_http(codigo, corpo):
    texto = corpo if isinstance(corpo, bytes) else json.dumps(corpo).encode()
    return urllib.error.HTTPError('https://api.mercadopago.com', codigo,
                                  'erro', {}, io.BytesIO(texto))


@pytest.fixture
def com_token(monkeypatch):
    monkeypatch.setattr(mercadopago, 'token', lambda: 'TEST-token-de-teste')


@pytest.fixture
def urlopen_falso(monkeypatch):
    registro = {'requisicoes': [], 'resposta': _RespostaFalsa({})}

    def _urlopen(requisicao, *_args, **_kwargs):
        registro['requisicoes'].append(requisicao)
        resposta = registro['resposta']
        if isinstance(resposta, Exception):
            raise resposta
        return resposta

    monkeypatch.setattr('urllib.request.urlopen', _urlopen)
    return registro


@pytest.fixture
def log_do_mp():
    """Handler proprio no logger do modulo, pelo mesmo motivo documentado em
    test_integracoes.py: `caplog` depende de propagacao ate a raiz e isso nao
    se sustenta na suite completa."""
    registros = []

    class _Coletor(logging.Handler):
        def emit(self, registro):
            registros.append(registro.getMessage())

    logger = logging.getLogger('adri.mercadopago')
    handler = _Coletor()
    nivel = logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.ERROR)
    try:
        yield registros
    finally:
        logger.removeHandler(handler)
        logger.setLevel(nivel)


# =============================================================================
# Configuracao
# =============================================================================
def test_sem_token_reporta_nao_configurado(monkeypatch):
    monkeypatch.setattr(mercadopago, 'token', lambda: '')
    assert mercadopago.esta_configurado() is False


def test_sem_token_nao_tenta_falar_com_a_rede(monkeypatch, urlopen_falso):
    """Falhar antes de sair e o que separa "nao configurado" de "a rede caiu"
    na mensagem que o operador ve."""
    monkeypatch.setattr(mercadopago, 'token', lambda: '')

    assert mercadopago.criar_cobranca_pix(150000, 'x', 'ref')['_erro'] is True
    assert mercadopago.obter_pagamento('123')['_erro'] is True
    assert urlopen_falso['requisicoes'] == []


# =============================================================================
# Criacao da cobranca
# =============================================================================
def test_cobranca_pix_traduz_a_resposta_para_o_que_a_tela_precisa(com_token, urlopen_falso):
    urlopen_falso['resposta'] = _RespostaFalsa({
        "id": 111222333,
        "status": "pending",
        "point_of_interaction": {"transaction_data": {
            "qr_code": "00020126580014BR.GOV.BCB.PIX",
            "qr_code_base64": "aGVsbG8=",
        }},
        "date_of_expiration": "2026-09-06T00:00:00.000-03:00",
    })

    resposta = mercadopago.criar_cobranca_pix(150000, 'Licenca', 'adri-licenca-abc')

    assert resposta['pagamento_id'] == '111222333'
    assert resposta['status'] == 'pending'
    assert resposta['pix_payload'].startswith('00020126')
    assert resposta['pix_qr_code'] == 'aGVsbG8='


def test_o_valor_vai_em_reais_e_nao_em_centavos(com_token, urlopen_falso):
    """O app conta em centavos; o Mercado Pago recebe reais. Errar a conversao
    cobraria R$ 150.000,00 por uma licenca de R$ 1.500,00."""
    urlopen_falso['resposta'] = _RespostaFalsa({"id": 1, "status": "pending"})

    mercadopago.criar_cobranca_pix(150000, 'Licenca', 'ref')

    corpo = json.loads(urlopen_falso['requisicoes'][0].data.decode())
    assert corpo['transaction_amount'] == 1500.00


def test_a_referencia_da_instalacao_vai_junto(com_token, urlopen_falso):
    """`external_reference` e o que liga o pagamento a esta maquina."""
    urlopen_falso['resposta'] = _RespostaFalsa({"id": 1, "status": "pending"})

    mercadopago.criar_cobranca_pix(150000, 'Licenca', 'adri-licenca-xyz')

    corpo = json.loads(urlopen_falso['requisicoes'][0].data.decode())
    assert corpo['external_reference'] == 'adri-licenca-xyz'
    assert corpo['payment_method_id'] == 'pix'


def test_a_criacao_leva_chave_de_idempotencia(com_token, urlopen_falso):
    """Sem ela, um clique duplo ou uma repeticao por timeout cria DUAS
    cobrancas -- e a segunda e dinheiro cobrado a mais de quem ja pagou."""
    urlopen_falso['resposta'] = _RespostaFalsa({"id": 1, "status": "pending"})

    mercadopago.criar_cobranca_pix(150000, 'Licenca', 'adri-licenca-xyz')

    cabecalhos = urlopen_falso['requisicoes'][0].headers
    chave = cabecalhos.get('X-idempotency-key') or cabecalhos.get('X-Idempotency-Key')
    assert chave and chave.startswith('adri-licenca-xyz')


def test_a_consulta_nao_leva_chave_de_idempotencia(com_token, urlopen_falso):
    """GET nao cria nada; mandar a chave ali seria ruido sem significado."""
    urlopen_falso['resposta'] = _RespostaFalsa({"id": 1, "status": "approved"})

    mercadopago.obter_pagamento('1')

    cabecalhos = urlopen_falso['requisicoes'][0].headers
    assert not (cabecalhos.get('X-idempotency-key')
                or cabecalhos.get('X-Idempotency-Key'))


# =============================================================================
# O que conta como pago
# =============================================================================
@pytest.mark.parametrize('status,esperado', [
    ('approved', True),
    ('pending', False),
    ('in_process', False),
    ('rejected', False),
    ('cancelled', False),
    ('refunded', False),
    ('charged_back', False),
])
def test_apenas_approved_libera_a_licenca(com_token, urlopen_falso, status, esperado):
    urlopen_falso['resposta'] = _RespostaFalsa({"id": 9, "status": status})
    assert mercadopago.obter_pagamento('9')['pago'] is esperado


def test_autorizado_nao_e_pago(com_token, urlopen_falso):
    """
    `authorized` e cartao autorizado e NAO capturado: dinheiro reservado, nao
    recebido. Liberar ali entregaria o produto por uma transacao que ainda
    pode nao se concretizar.
    """
    urlopen_falso['resposta'] = _RespostaFalsa({"id": 9, "status": "authorized"})
    assert mercadopago.obter_pagamento('9')['pago'] is False


@pytest.mark.parametrize('status', ['cancelled', 'rejected', 'refunded', 'charged_back'])
def test_status_terminais_sao_marcados_como_encerrados(com_token, urlopen_falso, status):
    """E o que permite a tela parar de perguntar em vez de girar para sempre."""
    urlopen_falso['resposta'] = _RespostaFalsa({"id": 9, "status": status})
    assert mercadopago.obter_pagamento('9')['encerrado'] is True


def test_pendente_nao_e_encerrado(com_token, urlopen_falso):
    urlopen_falso['resposta'] = _RespostaFalsa({"id": 9, "status": "pending"})
    assert mercadopago.obter_pagamento('9')['encerrado'] is False


# =============================================================================
# Falhas
# =============================================================================
def test_erro_http_vira_dicionario_e_nao_excecao(com_token, urlopen_falso):
    urlopen_falso['resposta'] = _erro_http(400, {"message": "invalid_parameter"})
    resposta = mercadopago.obter_pagamento('9')
    assert resposta['_erro'] is True
    assert resposta['_status'] == 400


def test_falha_de_rede_vira_dicionario_e_nao_excecao(com_token, urlopen_falso):
    urlopen_falso['resposta'] = urllib.error.URLError('sem rota')
    assert mercadopago.criar_cobranca_pix(150000, 'x', 'ref')['_erro'] is True


def test_a_recusa_nao_leva_o_corpo_bruto_para_o_log(com_token, urlopen_falso, log_do_mp):
    """
    Mesma regra adotada em asaas.py: o corpo de uma recusa repete o que foi
    enviado, e o app.log fica em %APPDATA% sem cifragem.
    """
    urlopen_falso['resposta'] = _erro_http(400, {
        "message": "invalid_parameter",
        "cause": [{"description": "payer.email invalido: maria@exemplo.com"}],
        "payer": {"email": "maria@exemplo.com"},
    })

    mercadopago.obter_pagamento('9')

    registrado = " | ".join(log_do_mp)
    assert registrado, "a recusa precisa continuar aparecendo no log"
    assert 'maria@exemplo.com' not in registrado
    assert 'invalid_parameter' in registrado
