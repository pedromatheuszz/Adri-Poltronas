"""
Emissao de cobranca sem cobrar o cliente duas vezes, e conciliacao sem webhook.

Emitir uma cobranca sao tres passos, e so o primeiro e o ultimo sao nossos:
chamar o Asaas, receber o id, gravar o id. Se o processo morrer entre a
chamada e a gravacao -- queda de energia, app fechado, resposta perdida no
caminho --, a cobranca existe no Asaas e o sistema nao sabe. O operador clica
de novo, e o cliente recebe DUAS cobrancas do mesmo valor.

Nada impedia isso: nem clique duplo, nem requisicoes simultaneas, nem emissao
sobre pagamento que ja tinha `asaas_payment_id`, nem sobre pagamento ja
recebido. As colunas que resolveriam (`asaas_external_reference`,
`asaas_emissao_estado`) existiam no banco desde a migracao de integridade e
nenhuma linha de codigo as usava.

A segunda metade do arquivo cobre a conciliacao. O webhook do Asaas NUNCA
chega numa instalacao normal: o Flask escuta em 127.0.0.1:5000 e um servidor
na internet nao alcanca o loopback da maquina do usuario. O sistema parecia
integrado e nao era -- o cliente pagava, o dinheiro entrava na conta do Asaas
e a cobranca seguia "Pendente" no ERP.
"""
import json
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

import asaas  # noqa: E402
import database  # noqa: E402
import app as app_module  # noqa: E402
from erp.financeiro import emissao, reconciliacao  # noqa: E402

ORIGEM_LOCAL = 'http://localhost'


@pytest.fixture
def client():
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as arquivo:
        caminho = arquivo.name

    original = database.DB_PATH
    database.DB_PATH = caminho
    app_module.app.config['TESTING'] = True
    with app_module.app.app_context():
        database.criar_tabela()

    yield app_module.app.test_client()

    database.DB_PATH = original
    os.unlink(caminho)


class AsaasFalso:
    """
    Duble do gateway que CONTA quantas cobrancas criou.

    A contagem e o coracao destes testes: o defeito nao aparece no estado
    final do banco, aparece no numero de cobrancas que o cliente recebe.
    """

    def __init__(self):
        self.cobrancas_criadas = []
        self.consultas_por_referencia = []
        self.status_por_id = {}
        self.falhar_criacao = False
        self.falhar_busca = False
        self.perder_resposta = False
        self._proximo_id = 1

    # -- interface consumida pelo codigo de producao --------------------
    def esta_configurado(self):
        return True

    def criar_cobranca_pix(self, customer, valor, vencimento, descricao="",
                           referencia_externa=""):
        return self._criar("PIX", customer, valor, referencia_externa)

    def criar_cobranca_boleto(self, customer, valor, vencimento, descricao="",
                              referencia_externa=""):
        return self._criar("BOLETO", customer, valor, referencia_externa)

    def obter_qr_code_pix(self, asaas_payment_id):
        return {"payload": "00020126...", "encodedImage": "iVBORw0KGgo="}

    def buscar_por_referencia_externa(self, referencia):
        self.consultas_por_referencia.append(referencia)
        if self.falhar_busca:
            return {"_erro": "timeout", "_status": 0}
        for cobranca in self.cobrancas_criadas:
            if cobranca["externalReference"] == referencia:
                return cobranca
        return None

    def obter_status_pagamento(self, asaas_payment_id):
        if asaas_payment_id in self.status_por_id:
            return {"status": self.status_por_id[asaas_payment_id]}
        return {"_erro": "nao encontrado", "_status": 404}

    def obter_pagamento(self, asaas_payment_id):
        return self.obter_status_pagamento(asaas_payment_id)

    # -- apoio ----------------------------------------------------------
    def _criar(self, tipo, customer, valor, referencia):
        if self.falhar_criacao:
            return {"_erro": "gateway fora do ar", "_status": 503}
        identificador = f"pay_{self._proximo_id}"
        self._proximo_id += 1
        cobranca = {
            "id": identificador,
            "billingType": tipo,
            "value": valor,
            "externalReference": referencia,
            "bankSlipUrl": "https://sandbox.asaas.com/boleto",
            "nossoNumero": "123456",
        }
        # A cobranca EXISTE no gateway mesmo quando a resposta se perde --
        # esse e justamente o cenario que quebrava o sistema.
        self.cobrancas_criadas.append(cobranca)
        self.status_por_id[identificador] = "PENDING"
        if self.perder_resposta:
            return {"_erro": "conexao encerrada", "_status": 0}
        return cobranca


@pytest.fixture
def gateway(monkeypatch):
    falso = AsaasFalso()
    for nome in ('esta_configurado', 'criar_cobranca_pix', 'criar_cobranca_boleto',
                 'obter_qr_code_pix', 'buscar_por_referencia_externa',
                 'obter_status_pagamento', 'obter_pagamento'):
        monkeypatch.setattr(asaas, nome, getattr(falso, nome))
    monkeypatch.setattr(
        database, 'obter_ou_criar_cliente_asaas',
        lambda *args, **kwargs: 'cus_000001',
    )
    return falso


def _cliente_e_pagamento(client, tipo='Pix'):
    client.post('/api/clientes', headers={'Origin': ORIGEM_LOCAL},
                data=json.dumps({
                    "nome": "Cliente Teste", "cep": "12345-678", "rua": "Rua Teste",
                    "bairro": "Centro", "cidade": "Sao Paulo",
                    "entrega_retirada": "Entrega",
                }), content_type='application/json')
    cliente_id = json.loads(client.get('/api/clientes').data)[0]['id']

    resposta = client.post('/api/pagamentos', headers={'Origin': ORIGEM_LOCAL},
                           data=json.dumps({
                               "cliente_id": cliente_id,
                               "cliente_nome": "Cliente Teste",
                               "valor": 250.00,
                               "descricao": "Poltrona",
                               "data_vencimento": "2030-01-10",
                               "tipo_pagamento": tipo,
                           }), content_type='application/json')
    return cliente_id, json.loads(resposta.data)['id']


def _gerar(client, pagamento_id):
    return client.post('/api/pagamentos/gerar-cobranca', headers={'Origin': ORIGEM_LOCAL},
                       data=json.dumps({"pagamento_id": pagamento_id}),
                       content_type='application/json')


# =============================================================================
# Emissao idempotente
# =============================================================================
def test_emissao_normal_cria_uma_cobranca(client, gateway):
    _, pagamento_id = _cliente_e_pagamento(client)

    resposta = _gerar(client, pagamento_id)

    assert resposta.status_code == 201
    assert len(gateway.cobrancas_criadas) == 1
    pagamento = database.obter_pagamento_por_id(pagamento_id)
    assert pagamento['asaas_payment_id'] == 'pay_1'
    assert pagamento['asaas_emissao_estado'] == emissao.ESTADO_CONCLUIDA
    assert pagamento['asaas_external_reference'].startswith('adri-')


def test_clicar_duas_vezes_nao_cobra_o_cliente_duas_vezes(client, gateway):
    """O defeito mais visivel: o botao respondia a cada clique."""
    _, pagamento_id = _cliente_e_pagamento(client)

    primeira = _gerar(client, pagamento_id)
    segunda = _gerar(client, pagamento_id)

    assert primeira.status_code == 201
    assert segunda.status_code == 200
    assert json.loads(segunda.data)['ja_existia'] is True
    assert len(gateway.cobrancas_criadas) == 1, "o cliente recebeu duas cobrancas"
    assert json.loads(segunda.data)['asaas_payment_id'] == 'pay_1'


def test_resposta_perdida_e_recuperada_em_vez_de_gerar_outra_cobranca(client, gateway):
    """
    O caso que motivou o mecanismo.

    A cobranca e criada no Asaas e a resposta se perde no caminho. O sistema
    fica sem o id. Sem a referencia externa nao ha como distinguir isso de
    "nao foi criada", e a proxima tentativa gera a segunda cobranca.
    """
    _, pagamento_id = _cliente_e_pagamento(client)

    gateway.perder_resposta = True
    falhou = _gerar(client, pagamento_id)
    assert falhou.status_code == 502
    assert len(gateway.cobrancas_criadas) == 1
    assert database.obter_pagamento_por_id(pagamento_id)['asaas_payment_id'] in ('', None)

    # Segunda tentativa: a rede voltou.
    gateway.perder_resposta = False
    recuperada = _gerar(client, pagamento_id)

    assert recuperada.status_code == 200
    assert json.loads(recuperada.data)['ja_existia'] is True
    assert len(gateway.cobrancas_criadas) == 1, "gerou uma segunda cobranca"
    assert database.obter_pagamento_por_id(pagamento_id)['asaas_payment_id'] == 'pay_1'
    assert gateway.consultas_por_referencia, "nao perguntou ao Asaas antes de emitir"


def test_consulta_que_falha_nao_autoriza_nova_emissao(client, gateway):
    """
    Nao saber e diferente de saber que nao existe.

    Se a consulta pela referencia falha, emitir seria exatamente o risco que
    o mecanismo evita. Melhor recusar e pedir para tentar de novo.
    """
    _, pagamento_id = _cliente_e_pagamento(client)

    gateway.perder_resposta = True
    _gerar(client, pagamento_id)
    gateway.perder_resposta = False
    gateway.falhar_busca = True

    resposta = _gerar(client, pagamento_id)

    assert resposta.status_code == 409
    assert len(gateway.cobrancas_criadas) == 1


def test_falha_do_gateway_preserva_a_referencia_para_a_proxima_tentativa(client, gateway):
    _, pagamento_id = _cliente_e_pagamento(client)
    gateway.falhar_criacao = True

    resposta = _gerar(client, pagamento_id)

    assert resposta.status_code == 502
    pagamento = database.obter_pagamento_por_id(pagamento_id)
    assert pagamento['asaas_emissao_estado'] == emissao.ESTADO_FALHOU
    assert pagamento['asaas_external_reference'].startswith('adri-')


def test_pagamento_recebido_nao_aceita_nova_cobranca(client, gateway):
    """Emitir sobre 'Recebido' cobraria de novo quem ja pagou."""
    _, pagamento_id = _cliente_e_pagamento(client)
    database.atualizar_pagamento(pagamento_id, status='Recebido',
                                 data_pagamento='2030-01-10')

    resposta = _gerar(client, pagamento_id)

    assert resposta.status_code == 409
    assert gateway.cobrancas_criadas == []


def test_reivindicacao_simultanea_tem_um_vencedor_so(client, gateway):
    """
    O compare-and-swap, exercitado direto.

    Duas requisicoes simultaneas nao podem ambas sair para a rede: a segunda
    nao tem como saber se a primeira ja criou a cobranca.
    """
    _, pagamento_id = _cliente_e_pagamento(client)

    referencia, _ = emissao.reivindicar(database.conectar, pagamento_id)
    assert referencia.startswith('adri-')

    with pytest.raises(emissao.EmissaoJaEmCurso):
        emissao.reivindicar(database.conectar, pagamento_id)


# =============================================================================
# Conciliacao: o que substitui o webhook inalcancavel
# =============================================================================
def test_conciliacao_marca_como_recebido_o_que_foi_pago(client, gateway):
    _, pagamento_id = _cliente_e_pagamento(client)
    _gerar(client, pagamento_id)

    # O cliente pagou. Numa instalacao real o webhook nunca chegaria aqui.
    gateway.status_por_id['pay_1'] = 'RECEIVED'

    resposta = client.post('/api/pagamentos/reconciliar', headers={'Origin': ORIGEM_LOCAL})

    assert resposta.status_code == 200
    resumo = json.loads(resposta.data)
    assert resumo['atualizadas'] == 1
    pagamento = database.obter_pagamento_por_id(pagamento_id)
    assert pagamento['status'] == 'Recebido'
    assert pagamento['data_pagamento']


def test_conciliacao_e_idempotente(client, gateway):
    _, pagamento_id = _cliente_e_pagamento(client)
    _gerar(client, pagamento_id)
    gateway.status_por_id['pay_1'] = 'RECEIVED'

    primeira = json.loads(client.post('/api/pagamentos/reconciliar',
                                      headers={'Origin': ORIGEM_LOCAL}).data)
    segunda = json.loads(client.post('/api/pagamentos/reconciliar',
                                     headers={'Origin': ORIGEM_LOCAL}).data)

    assert primeira['atualizadas'] == 1
    # Ja nao esta mais em aberto, entao nem e consultada de novo.
    assert segunda['atualizadas'] == 0


def test_status_desconhecido_do_gateway_e_ignorado(client, gateway):
    """Um palpite num campo financeiro e pior do que um campo desatualizado."""
    _, pagamento_id = _cliente_e_pagamento(client)
    _gerar(client, pagamento_id)
    gateway.status_por_id['pay_1'] = 'ALGUM_STATUS_NOVO_DO_ASAAS'

    resumo = json.loads(client.post('/api/pagamentos/reconciliar',
                                    headers={'Origin': ORIGEM_LOCAL}).data)

    assert resumo['atualizadas'] == 0
    assert database.obter_pagamento_por_id(pagamento_id)['status'] == 'Pendente'


def test_falha_de_consulta_nao_muda_nada(client, gateway):
    _, pagamento_id = _cliente_e_pagamento(client)
    _gerar(client, pagamento_id)
    gateway.status_por_id.pop('pay_1')  # a consulta passa a devolver erro

    resumo = json.loads(client.post('/api/pagamentos/reconciliar',
                                    headers={'Origin': ORIGEM_LOCAL}).data)

    assert resumo['falhas'] == 1
    assert resumo['atualizadas'] == 0
    assert database.obter_pagamento_por_id(pagamento_id)['status'] == 'Pendente'


def test_traducao_cobre_os_status_terminais_do_asaas():
    """Recebido, atrasado e cancelado sao os tres desfechos que mudam o que o
    dashboard mostra. Um deles faltando faz o numero mentir."""
    assert reconciliacao.TRADUCAO_DE_STATUS['RECEIVED'] == 'Recebido'
    assert reconciliacao.TRADUCAO_DE_STATUS['CONFIRMED'] == 'Recebido'
    assert reconciliacao.TRADUCAO_DE_STATUS['OVERDUE'] == 'Atrasado'
    assert reconciliacao.TRADUCAO_DE_STATUS['REFUNDED'] == 'Cancelado'


# =============================================================================
# Confirmacao manual: nao declara receita que ninguem recebeu
# =============================================================================
def test_confirmacao_manual_recusa_cobranca_ainda_aberta_no_asaas(client, gateway):
    """
    O clique marcava 'Recebido' sem perguntar nada a ninguem.

    E o pior tipo de erro num modulo financeiro: o numero errado parece certo.
    """
    _, pagamento_id = _cliente_e_pagamento(client)
    _gerar(client, pagamento_id)  # continua PENDING no gateway

    resposta = client.post(f'/api/pagamentos/{pagamento_id}/confirmar',
                           headers={'Origin': ORIGEM_LOCAL})

    assert resposta.status_code == 409
    assert json.loads(resposta.data)['pode_forcar'] is True
    assert database.obter_pagamento_por_id(pagamento_id)['status'] == 'Pendente'


def test_confirmacao_manual_aceita_quando_o_asaas_confirma(client, gateway):
    _, pagamento_id = _cliente_e_pagamento(client)
    _gerar(client, pagamento_id)
    gateway.status_por_id['pay_1'] = 'RECEIVED'

    resposta = client.post(f'/api/pagamentos/{pagamento_id}/confirmar',
                           headers={'Origin': ORIGEM_LOCAL})

    assert resposta.status_code == 200
    assert database.obter_pagamento_por_id(pagamento_id)['status'] == 'Recebido'


def test_forcar_exige_motivo(client, gateway):
    _, pagamento_id = _cliente_e_pagamento(client)
    _gerar(client, pagamento_id)

    resposta = client.post(f'/api/pagamentos/{pagamento_id}/confirmar',
                           headers={'Origin': ORIGEM_LOCAL},
                           data=json.dumps({"forcar": True}),
                           content_type='application/json')

    assert resposta.status_code == 400
    assert database.obter_pagamento_por_id(pagamento_id)['status'] == 'Pendente'


def test_forcar_com_motivo_confirma_e_deixa_rastro(client, gateway):
    """Pagamento feito por fora do gateway e legitimo. O que nao pode e ser
    indistinguivel de um erro depois."""
    cliente_id, pagamento_id = _cliente_e_pagamento(client)
    _gerar(client, pagamento_id)

    resposta = client.post(f'/api/pagamentos/{pagamento_id}/confirmar',
                           headers={'Origin': ORIGEM_LOCAL},
                           data=json.dumps({
                               "forcar": True,
                               "motivo": "Pago em dinheiro na retirada",
                           }),
                           content_type='application/json')

    assert resposta.status_code == 200
    assert database.obter_pagamento_por_id(pagamento_id)['status'] == 'Recebido'

    with database.conectar() as conexao:
        registros = conexao.execute(
            "SELECT detalhes FROM historico WHERE cliente_id=?", (cliente_id,)
        ).fetchall()
        eventos = conexao.execute(
            "SELECT acao FROM auditoria_eventos WHERE entidade='pagamento' "
            "AND entidade_id=?", (pagamento_id,)
        ).fetchall()

    assert any('Pago em dinheiro na retirada' in linha['detalhes'] for linha in registros), \
        "o motivo nao chegou ao historico do cliente"
    assert any(linha['acao'] == 'financeiro.recebivel.observacao_manual' for linha in eventos), \
        "a excecao nao ficou na trilha de auditoria"


def test_pagamento_sem_cobranca_no_gateway_pode_ser_confirmado_direto(client, gateway):
    """Dinheiro, transferencia combinada por fora: nao ha gateway com o que
    conferir, e exigir motivo aqui seria atrito sem ganho."""
    _, pagamento_id = _cliente_e_pagamento(client, tipo='Dinheiro')

    resposta = client.post(f'/api/pagamentos/{pagamento_id}/confirmar',
                           headers={'Origin': ORIGEM_LOCAL})

    assert resposta.status_code == 200
    assert database.obter_pagamento_por_id(pagamento_id)['status'] == 'Recebido'
