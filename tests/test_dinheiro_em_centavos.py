"""
Dinheiro em centavos inteiros, e as chaves estrangeiras de pedido.

PONTO FLUTUANTE NAO GUARDA DINHEIRO
`pagamentos.valor` e SQLite REAL, ou seja, IEEE 754 binario, que nao
representa 0,10 exatamente:

    >>> sum([33.33, 33.33, 33.34])
    99.99999999999999

O modulo comercial ja nascera certo -- `pedidos` guarda centavos e
`dinheiro.ratear` divide sem perder centavo. Mas o faturamento entregava o
resultado a `pagamentos` passando por `round(centavos / 100, 2)`, e o trabalho
do rateio se desfazia na conversao.

CHAVES ESTRANGEIRAS
`pagamentos.pedido_id` e `entregas_agendadas.pedido_id` foram acrescentadas por
ALTER TABLE, e SQLite nao aceita adicionar constraint por ALTER: as colunas
ficaram sem FK. Nada impedia uma parcela apontando para um pedido inexistente,
e apagar um pedido deixava parcelas orfas em silencio.
"""
import json
import os
import sqlite3
import sys
from contextlib import closing

import pytest

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(RAIZ, 'backend'))

import database  # noqa: E402
import migrations_manager  # noqa: E402
import app as app_module  # noqa: E402
from erp.core import dinheiro  # noqa: E402

ORIGEM_LOCAL = 'http://localhost'


@pytest.fixture
def client(tmp_path):
    caminho = str(tmp_path / "centavos.db")
    original = database.DB_PATH
    database.DB_PATH = caminho
    app_module.app.config['TESTING'] = True
    with app_module.app.app_context():
        database.criar_tabela()

    yield app_module.app.test_client()

    database.DB_PATH = original


def _cliente(client, nome="Cliente Centavos"):
    client.post('/api/clientes', headers={'Origin': ORIGEM_LOCAL},
                data=json.dumps({
                    "nome": nome, "cep": "12345-678", "rua": "Rua A",
                    "bairro": "Centro", "cidade": "Santos",
                    "entrega_retirada": "Entrega",
                }), content_type='application/json')
    return json.loads(client.get('/api/clientes').data)[0]['id']


# =============================================================================
# A soma das parcelas fecha com o total do pedido
# =============================================================================
@pytest.mark.parametrize("total_centavos,parcelas", [
    (10000, 3),    # R$ 100,00 em 3 -- o caso classico: 33,33 + 33,33 + 33,34
    (10, 3),       # dez centavos em tres
    (99999, 7),
    (1, 1),
    (250050, 12),
])
def test_soma_das_parcelas_e_exatamente_o_total(total_centavos, parcelas):
    valores = dinheiro.ratear(total_centavos, parcelas)
    assert sum(valores) == total_centavos
    assert len(valores) == parcelas


def test_faturamento_grava_centavos_sem_passar_por_float(client):
    """
    O teste que fecha o circuito: do rateio ate a linha em `pagamentos`.

    Antes, `inserir_parcela` recebia `round(centavos / 100, 2)` e gravava o
    float. A soma das tres parcelas de um pedido de R$ 100,00 nao voltava a
    100,00.
    """
    cliente_id = _cliente(client)

    produto = client.post('/api/produtos', headers={'Origin': ORIGEM_LOCAL},
                          data=json.dumps({
                              "codigo": "POLT-1", "descricao": "Poltrona",
                              "unidade": "UN", "preco_venda_centavos": 10000,
                          }), content_type='application/json')
    produto_id = json.loads(produto.data)['id']

    pedido = client.post('/api/pedidos', headers={'Origin': ORIGEM_LOCAL},
                         data=json.dumps({
                             "cliente_id": cliente_id,
                             "data_entrega_prevista": "2030-01-10",
                         }), content_type='application/json')
    pedido_id = json.loads(pedido.data)['id']

    client.post(f'/api/pedidos/{pedido_id}/itens', headers={'Origin': ORIGEM_LOCAL},
                data=json.dumps({
                    "produto_id": produto_id, "quantidade": 1,
                    # `preco_unitario` em reais: o servico converte para
                    # centavos na borda, via `dinheiro.para_centavos`.
                    "preco_unitario": "100.00",
                }), content_type='application/json')

    client.post(f'/api/pedidos/{pedido_id}/abertura', headers={'Origin': ORIGEM_LOCAL})
    client.post(f'/api/pedidos/{pedido_id}/aprovacao', headers={'Origin': ORIGEM_LOCAL})
    resposta = client.post(f'/api/pedidos/{pedido_id}/faturamento', headers={'Origin': ORIGEM_LOCAL},
                           data=json.dumps({
                               "parcelas": 3,
                               "primeiro_vencimento": "2030-02-10",
                               "forma_pagamento": "Pix",
                           }), content_type='application/json')

    assert resposta.status_code == 200, resposta.data

    with database.conectar() as conexao:
        linhas = conexao.execute(
            "SELECT valor, valor_centavos FROM pagamentos WHERE pedido_id = ? "
            "ORDER BY parcela", (pedido_id,)
        ).fetchall()

    assert len(linhas) == 3
    centavos = [linha["valor_centavos"] for linha in linhas]
    assert centavos == [3334, 3333, 3333] or sum(centavos) == 10000
    assert sum(centavos) == 10000, "as parcelas nao somam o total do pedido"

    # E o `valor` REAL segue coerente com os centavos, para as consultas que
    # ainda dependem dele.
    for linha in linhas:
        assert round(linha["valor"] * 100) == linha["valor_centavos"]


# =============================================================================
# Escrita dupla: as duas colunas nunca divergem
# =============================================================================
def test_recebimento_avulso_deriva_os_centavos(client):
    cliente_id = _cliente(client)
    resposta = client.post('/api/pagamentos', headers={'Origin': ORIGEM_LOCAL},
                           data=json.dumps({
                               "cliente_id": cliente_id,
                               "cliente_nome": "Cliente Centavos",
                               "valor": 1234.56,
                               "descricao": "Avulso",
                               "data_vencimento": "2030-01-10",
                               "tipo_pagamento": "Pix",
                           }), content_type='application/json')
    pagamento_id = json.loads(resposta.data)['id']

    with database.conectar() as conexao:
        linha = conexao.execute(
            "SELECT valor, valor_centavos FROM pagamentos WHERE id = ?", (pagamento_id,)
        ).fetchone()

    assert linha["valor_centavos"] == 123456
    assert linha["valor"] == 1234.56


def test_editar_o_valor_leva_os_centavos_junto(client):
    """Deixar `valor` mudar sozinho faria `valor_centavos` guardar o numero
    antigo -- divergencia silenciosa ate alguem comparar os dois."""
    cliente_id = _cliente(client)
    resposta = client.post('/api/pagamentos', headers={'Origin': ORIGEM_LOCAL},
                           data=json.dumps({
                               "cliente_id": cliente_id,
                               "cliente_nome": "Cliente Centavos",
                               "valor": 100.00,
                               "descricao": "Avulso",
                               "data_vencimento": "2030-01-10",
                               "tipo_pagamento": "Pix",
                           }), content_type='application/json')
    pagamento_id = json.loads(resposta.data)['id']

    database.atualizar_pagamento(pagamento_id, valor=250.75)

    with database.conectar() as conexao:
        linha = conexao.execute(
            "SELECT valor, valor_centavos FROM pagamentos WHERE id = ?", (pagamento_id,)
        ).fetchone()

    assert linha["valor"] == 250.75
    assert linha["valor_centavos"] == 25075


def test_valores_com_dizima_nao_perdem_centavo(client):
    """`CAST(x * 100 AS INTEGER)` trunca. Sobre uma base inteira, um centavo
    por linha nao e arredondamento -- e erro."""
    cliente_id = _cliente(client)
    for valor, esperado in [(0.07, 7), (1.10, 110), (19.99, 1999), (0.29, 29)]:
        resposta = client.post('/api/pagamentos', headers={'Origin': ORIGEM_LOCAL},
                               data=json.dumps({
                                   "cliente_id": cliente_id,
                                   "cliente_nome": "Cliente Centavos",
                                   "valor": valor,
                                   "descricao": f"Valor {valor}",
                                   "data_vencimento": "2030-01-10",
                                   "tipo_pagamento": "Pix",
                               }), content_type='application/json')
        pagamento_id = json.loads(resposta.data)['id']
        with database.conectar() as conexao:
            centavos = conexao.execute(
                "SELECT valor_centavos FROM pagamentos WHERE id = ?", (pagamento_id,)
            ).fetchone()[0]
        assert centavos == esperado, f"{valor} virou {centavos} em vez de {esperado}"


# =============================================================================
# Chaves estrangeiras de pedido
# =============================================================================
def test_migrations_criam_a_fk_de_pagamentos_para_pedidos(tmp_path, monkeypatch):
    caminho = tmp_path / "fk.db"
    monkeypatch.setattr(database, "DB_PATH", str(caminho))
    migrations_manager.aplicar_migrações()

    with closing(sqlite3.connect(caminho)) as conexao:
        fks_pagamentos = conexao.execute("PRAGMA foreign_key_list(pagamentos)").fetchall()
        fks_entregas = conexao.execute("PRAGMA foreign_key_list(entregas_agendadas)").fetchall()
        colunas = {linha[1] for linha in conexao.execute("PRAGMA table_info(pagamentos)")}

    assert "valor_centavos" in colunas
    assert any(fk[2] == "pedidos" for fk in fks_pagamentos), \
        "pagamentos.pedido_id continua sem FK"
    assert any(fk[2] == "pedidos" for fk in fks_entregas), \
        "entregas_agendadas.pedido_id continua sem FK"


def test_parcela_apontando_para_pedido_inexistente_e_recusada(client):
    """Sem a FK, nada impedia -- e apagar um pedido deixava parcelas orfas."""
    cliente_id = _cliente(client)
    with pytest.raises(sqlite3.IntegrityError):
        with database.conectar() as conexao:
            conexao.execute(
                "INSERT INTO pagamentos (cliente_id, cliente_nome, valor, valor_centavos, "
                "descricao, status, data_vencimento, tipo_pagamento, pedido_id) "
                "VALUES (?, 'X', 10.0, 1000, 'Orfa', 'Pendente', '2030-01-10', 'Pix', 999999)",
                (cliente_id,),
            )


def test_backfill_converte_o_que_ja_existia(tmp_path, monkeypatch):
    """
    Um banco que ja tinha lancamentos precisa sair da migration com os
    centavos preenchidos -- senao o primeiro relatorio que lesse a coluna nova
    veria zero onde ha dinheiro.
    """
    caminho = tmp_path / "legado.db"
    monkeypatch.setattr(database, "DB_PATH", str(caminho))

    # Sobe ate a revisao ANTERIOR a que acrescenta a coluna.
    import alembic.command
    alembic.command.upgrade(migrations_manager._config(), "e2a9c4d70f61")

    with closing(sqlite3.connect(caminho)) as conexao:
        conexao.execute("INSERT INTO clientes (nome, cep, rua, bairro, cidade) "
                        "VALUES ('Antigo', '11000-000', 'Rua', 'Centro', 'Santos')")
        for valor in (33.33, 1234.56, 0.07):
            conexao.execute(
                "INSERT INTO pagamentos (cliente_id, cliente_nome, valor, descricao, "
                "status, data_vencimento, tipo_pagamento) "
                "VALUES (1, 'Antigo', ?, 'Legado', 'Pendente', '2030-01-10', 'Pix')",
                (valor,),
            )
        conexao.commit()

    migrations_manager.aplicar_migrações()

    with closing(sqlite3.connect(caminho)) as conexao:
        centavos = [linha[0] for linha in conexao.execute(
            "SELECT valor_centavos FROM pagamentos ORDER BY id")]

    assert centavos == [3333, 123456, 7]
