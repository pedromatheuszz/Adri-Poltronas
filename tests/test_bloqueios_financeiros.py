"""
Os tres bloqueios financeiros apontados na reavaliacao tecnica da 1.2.1.

Todos os tres tem a mesma forma: uma regra que existia na cabeca de quem
escreveu, e nao no codigo. O sistema se comportava bem porque a tela pedia as
coisas na ordem certa -- e regra que depende de o cliente se comportar nao e
regra, e uma requisicao fora dessa ordem passava.

1. EMISSAO TRAVADA PARA SEMPRE
   `iniciada` era um estado absorvente. Processo encerrado entre reivindicar e
   chamar o Asaas deixava o pagamento em 409 permanente: a proxima tentativa
   consultava o gateway, nao achava cobranca nenhuma, e ainda assim nao
   conseguia reivindicar, porque `iniciada` nao estava na lista de estados
   reivindicaveis. A unica saida era mexer no banco na mao.

2. O PUT COMO PORTA DOS FUNDOS
   Aceitava `status` no corpo e gravava direto -- dava para marcar 'Recebido'
   sem passar pela conferencia com o gateway. E aceitava mudar valor e
   vencimento de uma cobranca ja emitida, deixando o boleto que o cliente tem
   na mao diferente do que o ERP mostra.

3. CANCELAMENTO DIVERGENTE
   Com `asaas_payment_id` e sem chave configurada, cancelava so localmente: o
   ERP dizia "cancelado", o cliente recebia a cobranca e pagava. E 'Atrasado'
   nao era cancelavel, embora vencer nao quite nem cancele nada -- eram
   justamente as cobrancas mais antigas que nao podiam ser encerradas.
"""
import datetime
import json
import os
import sys
import tempfile

import pytest

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(RAIZ, 'backend'))

import asaas  # noqa: E402
import database  # noqa: E402
import app as app_module  # noqa: E402
from erp.financeiro import emissao  # noqa: E402

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
    """Duble que conta cobrancas criadas e permite simular queda."""

    def __init__(self):
        self.cobrancas = []
        self.cancelamentos = []
        self.configurado = True
        self.morrer_apos_criar = False
        self._proximo = 1

    def esta_configurado(self):
        return self.configurado

    def criar_cobranca_pix(self, *a, referencia_externa="", **k):
        return self._criar(referencia_externa)

    def criar_cobranca_boleto(self, *a, referencia_externa="", **k):
        return self._criar(referencia_externa)

    def obter_qr_code_pix(self, _id):
        return {"payload": "000201", "encodedImage": "iVBOR"}

    def buscar_por_referencia_externa(self, referencia):
        for c in self.cobrancas:
            if c["externalReference"] == referencia:
                return c
        return None

    def obter_status_pagamento(self, _id):
        return {"status": "PENDING"}

    def cancelar_pagamento(self, asaas_payment_id):
        self.cancelamentos.append(asaas_payment_id)
        return {"deleted": True}

    def _criar(self, referencia):
        identificador = f"pay_{self._proximo}"
        self._proximo += 1
        self.cobrancas.append({
            "id": identificador, "externalReference": referencia,
            "bankSlipUrl": "https://sandbox.asaas.com/b", "nossoNumero": "1",
        })
        if self.morrer_apos_criar:
            # A cobranca EXISTE no gateway; a resposta se perdeu.
            return {"_erro": "conexao encerrada", "_status": 0}
        return self.cobrancas[-1]


@pytest.fixture
def gateway(monkeypatch):
    falso = AsaasFalso()
    for nome in ('esta_configurado', 'criar_cobranca_pix', 'criar_cobranca_boleto',
                 'obter_qr_code_pix', 'buscar_por_referencia_externa',
                 'obter_status_pagamento', 'cancelar_pagamento'):
        monkeypatch.setattr(asaas, nome, getattr(falso, nome))
    monkeypatch.setattr(database, 'obter_ou_criar_cliente_asaas',
                        lambda *a, **k: 'cus_1')
    return falso


def _pagamento(client, tipo='Pix', status='Pendente'):
    client.post('/api/clientes', headers={'Origin': ORIGEM_LOCAL},
                data=json.dumps({
                    "nome": "Cliente", "cep": "11000-000", "rua": "Rua A",
                    "bairro": "Centro", "cidade": "Santos",
                    "entrega_retirada": "Entrega",
                }), content_type='application/json')
    cliente_id = json.loads(client.get('/api/clientes').data)[0]['id']

    resposta = client.post('/api/pagamentos', headers={'Origin': ORIGEM_LOCAL},
                           data=json.dumps({
                               "cliente_id": cliente_id, "cliente_nome": "Cliente",
                               "valor": 250.00, "descricao": "Poltrona",
                               "data_vencimento": "2030-01-10",
                               "tipo_pagamento": tipo, "status": status,
                           }), content_type='application/json')
    return cliente_id, json.loads(resposta.data)['id']


def _gerar(client, pagamento_id):
    return client.post('/api/pagamentos/gerar-cobranca', headers={'Origin': ORIGEM_LOCAL},
                       data=json.dumps({"pagamento_id": pagamento_id}),
                       content_type='application/json')


def _envelhecer_concessao(pagamento_id, segundos):
    """Recua `asaas_emissao_inicio` no tempo, simulando o relogio andando."""
    momento = datetime.datetime.now() - datetime.timedelta(seconds=segundos)
    with database.conectar() as conexao:
        conexao.execute(
            "UPDATE pagamentos SET asaas_emissao_inicio=? WHERE id=?",
            (momento.isoformat(timespec="seconds"), pagamento_id),
        )


# =============================================================================
# 1. Emissao travada em `iniciada`
# =============================================================================
def test_processo_encerrado_no_meio_nao_trava_a_emissao_para_sempre(client, gateway):
    """
    A regressao central da reavaliacao.

    Simula o processo morrendo depois de reivindicar e ANTES de chamar o
    Asaas: a reivindicacao acontece, e nada mais. Antes da concessao com
    expiracao, o pagamento respondia 409 indefinidamente.
    """
    _, pagamento_id = _pagamento(client)

    # O processo morreu aqui. Fica so o registro da intencao.
    emissao.reivindicar(database.conectar, pagamento_id)
    assert database.obter_pagamento_por_id(pagamento_id)['asaas_emissao_estado'] \
        == emissao.ESTADO_INICIADA

    # Enquanto a concessao vale, a recusa e correta: pode haver outra
    # requisicao em voo, e emitir agora duplicaria a cobranca.
    assert _gerar(client, pagamento_id).status_code == 409
    assert gateway.cobrancas == []

    # Passado o prazo, a emissao destrava.
    _envelhecer_concessao(pagamento_id, emissao.VALIDADE_DA_CONCESSAO_S + 60)
    resposta = _gerar(client, pagamento_id)

    assert resposta.status_code == 201, resposta.data
    assert len(gateway.cobrancas) == 1
    assert database.obter_pagamento_por_id(pagamento_id)['asaas_payment_id'] == 'pay_1'


def test_concessao_viva_ainda_bloqueia_a_segunda_requisicao(client, gateway):
    """A expiracao nao pode enfraquecer a exclusao mutua: dois cliques
    simultaneos continuam produzindo um vencedor so."""
    _, pagamento_id = _pagamento(client)

    emissao.reivindicar(database.conectar, pagamento_id)
    with pytest.raises(emissao.EmissaoJaEmCurso):
        emissao.reivindicar(database.conectar, pagamento_id)


def test_concessao_expirada_e_retomada_uma_vez_so(client, gateway):
    """Retomar renova o relogio -- senao todas as requisicoes represadas
    entrariam juntas no instante em que a concessao vence."""
    _, pagamento_id = _pagamento(client)
    emissao.reivindicar(database.conectar, pagamento_id)
    _envelhecer_concessao(pagamento_id, emissao.VALIDADE_DA_CONCESSAO_S + 60)

    emissao.reivindicar(database.conectar, pagamento_id)
    with pytest.raises(emissao.EmissaoJaEmCurso):
        emissao.reivindicar(database.conectar, pagamento_id)


def test_retomada_nao_duplica_cobranca_que_o_gateway_ja_tem(client, gateway):
    """A expiracao destrava, mas a reconciliacao continua vindo antes: se a
    tentativa anterior chegou a criar a cobranca, ela e recuperada."""
    _, pagamento_id = _pagamento(client)

    gateway.morrer_apos_criar = True
    assert _gerar(client, pagamento_id).status_code == 502
    assert len(gateway.cobrancas) == 1

    gateway.morrer_apos_criar = False
    _envelhecer_concessao(pagamento_id, emissao.VALIDADE_DA_CONCESSAO_S + 60)
    resposta = _gerar(client, pagamento_id)

    assert resposta.status_code == 200
    assert json.loads(resposta.data)['ja_existia'] is True
    assert len(gateway.cobrancas) == 1, "a retomada gerou uma segunda cobranca"


def test_retomada_fica_registrada_na_auditoria(client, gateway):
    """Uma tentativa que nao chegou ao fim e informacao operacional: quem
    conferir depois precisa conseguir ver que houve retomada."""
    _, pagamento_id = _pagamento(client)
    emissao.reivindicar(database.conectar, pagamento_id)
    _envelhecer_concessao(pagamento_id, emissao.VALIDADE_DA_CONCESSAO_S + 60)

    emissao.reivindicar(database.conectar, pagamento_id)

    with database.conectar() as conexao:
        eventos = conexao.execute(
            "SELECT valores_novos FROM auditoria_eventos "
            "WHERE entidade='pagamento' AND entidade_id=? "
            "AND acao='financeiro.cobranca.emissao_iniciada'",
            (str(pagamento_id),),
        ).fetchall()

    # Compara o VALOR, e nao o texto: `json.dumps` do SQLite grava sem espaco
    # depois dos dois-pontos, e uma assercao sobre a forma quebraria na
    # primeira mudanca de serializador.
    marcadas = [
        json.loads(e['valores_novos'] or '{}').get('retomada_de_concessao_expirada')
        for e in eventos
    ]
    assert marcadas.count(True) == 1, f"retomada nao registrada uma vez: {marcadas}"


# =============================================================================
# 2. O PUT nao e mais porta dos fundos
# =============================================================================
def _put(client, pagamento_id, cliente_id, **campos):
    corpo = {
        "cliente_id": cliente_id, "cliente_nome": "Cliente",
        "valor": 250.00, "descricao": "Poltrona",
        "data_vencimento": "2030-01-10", "tipo_pagamento": "Pix",
    }
    corpo.update(campos)
    return client.put(f'/api/pagamentos/{pagamento_id}', headers={'Origin': ORIGEM_LOCAL},
                      data=json.dumps(corpo), content_type='application/json')


def test_put_nao_marca_como_recebido(client, gateway):
    """Era o atalho que contornava a conferencia com o gateway."""
    cliente_id, pagamento_id = _pagamento(client)

    resposta = _put(client, pagamento_id, cliente_id, status="Recebido")

    assert resposta.status_code == 409
    assert database.obter_pagamento_por_id(pagamento_id)['status'] == 'Pendente'


def test_put_nao_altera_valor_de_cobranca_ja_emitida(client, gateway):
    """O boleto que o cliente tem na mao nao muda porque alguem editou o
    banco local."""
    cliente_id, pagamento_id = _pagamento(client)
    assert _gerar(client, pagamento_id).status_code == 201

    resposta = _put(client, pagamento_id, cliente_id, valor=999.00)

    assert resposta.status_code == 409
    assert 'valor' in json.loads(resposta.data)['campos_bloqueados']
    assert database.obter_pagamento_por_id(pagamento_id)['valor'] == 250.00


def test_put_nao_altera_vencimento_de_cobranca_ja_emitida(client, gateway):
    cliente_id, pagamento_id = _pagamento(client)
    _gerar(client, pagamento_id)

    resposta = _put(client, pagamento_id, cliente_id, data_vencimento="2031-12-31")

    assert resposta.status_code == 409
    assert 'data_vencimento' in json.loads(resposta.data)['campos_bloqueados']


def test_put_ainda_edita_descricao_de_cobranca_emitida(client, gateway):
    """Descricao nao sai no boleto. Bloquear tudo seria trocar um defeito por
    uma tela inutil."""
    cliente_id, pagamento_id = _pagamento(client)
    _gerar(client, pagamento_id)

    resposta = _put(client, pagamento_id, cliente_id, descricao="Poltrona de couro")

    assert resposta.status_code == 200
    assert database.obter_pagamento_por_id(pagamento_id)['descricao'] == 'Poltrona de couro'


def test_put_reenviando_o_mesmo_valor_nao_e_bloqueado(client, gateway):
    """`250.0` e `"250.00"` sao o mesmo dinheiro. Tratar reenvio de formulario
    como tentativa de alteracao recusaria edicao legitima."""
    cliente_id, pagamento_id = _pagamento(client)
    _gerar(client, pagamento_id)

    resposta = _put(client, pagamento_id, cliente_id,
                    valor="250.00", descricao="Outra")

    assert resposta.status_code == 200


def test_put_muda_valor_enquanto_nao_ha_cobranca_emitida(client, gateway):
    """Sem cobranca no gateway nao ha divergencia possivel."""
    cliente_id, pagamento_id = _pagamento(client)

    resposta = _put(client, pagamento_id, cliente_id, valor=300.00)

    assert resposta.status_code == 200
    assert database.obter_pagamento_por_id(pagamento_id)['valor'] == 300.00


# =============================================================================
# 3. Cancelamento nao diverge do gateway
# =============================================================================
def test_cancelar_cobranca_emitida_sem_chave_configurada_e_recusado(client, gateway):
    """
    O pior desfecho possivel: o ERP diz "cancelado", o cliente recebe a
    cobranca e paga, e ninguem concilia.
    """
    _, pagamento_id = _pagamento(client)
    _gerar(client, pagamento_id)

    gateway.configurado = False
    resposta = client.delete(f'/api/pagamentos/{pagamento_id}',
                             headers={'Origin': ORIGEM_LOCAL})

    assert resposta.status_code == 503
    assert gateway.cancelamentos == []
    assert database.obter_pagamento_por_id(pagamento_id)['status'] == 'Pendente'


def test_cancelar_lancamento_sem_cobranca_no_gateway_funciona_sem_chave(client, gateway):
    """Dinheiro, transferencia por fora: nao ha nada no Asaas para encerrar."""
    _, pagamento_id = _pagamento(client, tipo='Dinheiro')

    gateway.configurado = False
    resposta = client.delete(f'/api/pagamentos/{pagamento_id}',
                             headers={'Origin': ORIGEM_LOCAL})

    assert resposta.status_code == 200
    assert database.obter_pagamento_por_id(pagamento_id)['status'] == 'Cancelado'


def test_cobranca_atrasada_pode_ser_cancelada(client, gateway):
    """Vencer nao quita nem cancela: o cliente continua com um Pix vivo.
    Recusar o cancelamento dessas era recusar justamente as que mais precisam
    ser encerradas."""
    _, pagamento_id = _pagamento(client)
    _gerar(client, pagamento_id)
    with database.conectar() as conexao:
        conexao.execute("UPDATE pagamentos SET status='Atrasado' WHERE id=?",
                        (pagamento_id,))

    resposta = client.delete(f'/api/pagamentos/{pagamento_id}',
                             headers={'Origin': ORIGEM_LOCAL})

    assert resposta.status_code == 200
    assert gateway.cancelamentos == ['pay_1'], "nao encerrou a cobranca no gateway"
    assert database.obter_pagamento_por_id(pagamento_id)['status'] == 'Cancelado'


def test_cobranca_recebida_continua_nao_cancelavel(client, gateway):
    """Cancelar dinheiro que ja entrou apagaria receita real."""
    _, pagamento_id = _pagamento(client, tipo='Dinheiro', status='Recebido')

    resposta = client.delete(f'/api/pagamentos/{pagamento_id}',
                             headers={'Origin': ORIGEM_LOCAL})

    assert resposta.status_code == 400
    assert database.obter_pagamento_por_id(pagamento_id)['status'] == 'Recebido'
