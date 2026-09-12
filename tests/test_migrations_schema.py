"""
O schema que TODA instalacao nova recebe.

Existe uma lacuna estrutural nesta suite que custou um defeito real: as
fixtures montam o banco por `database.criar_tabela()`, que cai no
`schema_fallback` -- SQL cru, escrito a mao. Mas nenhuma instalacao usa esse
caminho: quem cria o banco na maquina da cliente e o Alembic.

Os dois schemas divergiram sem que nada reclamasse. O `schema_fallback`
escrevia `DEFAULT 'Pendente'`, correto; a migration inicial declarou
`server_default="'Pendente'"`, que o SQLAlchemy aspeia DE NOVO, produzindo
`DEFAULT '''Pendente'''` -- e gravando a string `'Pendente'`, com apostrofos
dentro. Toda consulta que filtra por esses valores errava em silencio, so na
instalacao real, e passava verde em 619 testes.

Estes testes exercitam o schema das migrations. Nao substituem os demais: o
que eles cobrem e a fronteira entre o que o Alembic constroi e o que o codigo
de producao espera encontrar.
"""
import os
import sqlite3
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

import database  # noqa: E402
import migrations_manager  # noqa: E402
import validators  # noqa: E402
from erp.comercial import repositorio  # noqa: E402


@pytest.fixture
def banco_das_migrations(tmp_path, monkeypatch):
    """Banco construido do zero pelo Alembic, como numa instalacao nova."""
    caminho = tmp_path / "instalacao_nova.db"
    monkeypatch.setattr(database, "DB_PATH", str(caminho))
    migrations_manager.aplicar_migrações()
    return str(caminho)


def _defaults(caminho: str, tabela: str) -> dict:
    con = sqlite3.connect(caminho)
    try:
        return {
            linha[1]: linha[4]
            for linha in con.execute(f"PRAGMA table_info({tabela})")  # noqa: S608 - nome de tabela literal do proprio teste
        }
    finally:
        con.close()


# =============================================================================
# Os DEFAULT precisam gravar o valor, nao o valor entre aspas
# =============================================================================
@pytest.mark.parametrize('tabela, coluna, esperado', [
    ('entregas_agendadas', 'status', 'Pendente'),
    ('pagamentos', 'status', 'Pendente'),
    ('pagamentos', 'tipo_pagamento', 'Pix'),
])
def test_default_de_status_nao_carrega_aspas(banco_das_migrations, tabela, coluna, esperado):
    """
    `DEFAULT '''Pendente'''` guarda dez caracteres, e nenhum `IN ('Pendente')`
    casa com eles. O erro nao levanta excecao -- so nao encontra nada.
    """
    atual = _defaults(banco_das_migrations, tabela)[coluna]
    assert atual == f"'{esperado}'", (
        f"{tabela}.{coluna} tem DEFAULT {atual!r}; esperado {esperado!r} aspeado uma vez so"
    )


def test_entrega_criada_pelo_default_casa_com_os_status_conhecidos(banco_das_migrations):
    """A prova que interessa: o valor GRAVADO, e nao o texto do DDL."""
    con = sqlite3.connect(banco_das_migrations)
    con.execute("INSERT INTO clientes (nome, cep, rua, bairro, cidade, entrega_retirada) "
                "VALUES ('C', '89200-000', 'R', 'B', 'Joinville', 'Entrega')")
    con.execute("INSERT INTO entregas_agendadas (cliente_id, cliente_nome, data_entrega) "
                "VALUES (1, 'C', '2030-01-01')")
    con.commit()
    gravado = con.execute("SELECT status FROM entregas_agendadas").fetchone()[0]
    con.close()

    assert gravado == 'Pendente'
    assert gravado in validators.OPCOES_STATUS_ENTREGA, (
        f"status {gravado!r} nao esta entre os validos: {validators.OPCOES_STATUS_ENTREGA}"
    )


# =============================================================================
# A correcao do BUG-06 precisa valer no schema das migrations
# =============================================================================
def test_cancelar_pedido_cancela_a_entrega_em_banco_de_migration(banco_das_migrations):
    """
    Este e o teste que faltava.

    `cancelar_entregas_do_pedido()` filtra por `status IN ('Pendente', ...)`.
    Com o DEFAULT defeituoso ele encontrava zero linhas, e cancelar um pedido
    deixava a entrega viva na agenda -- gerando "ENTREGA ATRASADA" para um
    pedido que ninguem ia entregar. Passava verde na suite porque a suite usava
    o outro schema.
    """
    con = sqlite3.connect(banco_das_migrations)
    con.execute("INSERT INTO clientes (nome, cep, rua, bairro, cidade, entrega_retirada) "
                "VALUES ('C', '89200-000', 'R', 'B', 'Joinville', 'Entrega')")
    con.execute("INSERT INTO pedidos (numero, cliente_id, cliente_nome, data_emissao, situacao) "
                "VALUES ('PED-2026-000001', 1, 'C', '2026-01-01', 'aprovado')")
    con.execute("INSERT INTO entregas_agendadas (cliente_id, cliente_nome, data_entrega, pedido_id) "
                "VALUES (1, 'C', '2030-01-01', 1)")
    con.commit()

    canceladas = repositorio.cancelar_entregas_do_pedido(con, 1)
    con.commit()
    status = con.execute("SELECT status FROM entregas_agendadas").fetchone()[0]
    con.close()

    assert canceladas == 1, "a entrega vinculada nao foi encontrada pelo filtro de status"
    assert status == 'Cancelada'


# =============================================================================
# A correcao do BUG-04 precisa valer no schema das migrations
# =============================================================================
def test_parcela_criada_pelo_default_impede_a_exclusao(banco_das_migrations):
    """
    A trava conta parcelas `status IN ('Pendente', 'Atrasado')`. Com o valor
    aspeado, uma parcela pendente nao era contada e o cliente era excluido
    apesar de dever -- o inverso exato do que a correcao pediu.

    A parcela nasce aqui SEM status explicito, para que o DEFAULT seja quem o
    grava -- e com `pedido_id`, como toda parcela que o faturamento emite.
    """
    con = sqlite3.connect(banco_das_migrations)
    con.execute("INSERT INTO clientes (nome, cep, rua, bairro, cidade, entrega_retirada) "
                "VALUES ('Devedora', '89200-000', 'R', 'B', 'Joinville', 'Entrega')")
    con.execute("INSERT INTO pedidos (numero, cliente_id, cliente_nome, data_emissao, situacao) "
                "VALUES ('PED-2026-000001', 1, 'Devedora', '2026-01-01', 'faturado')")
    con.execute("INSERT INTO pagamentos (cliente_id, cliente_nome, valor, valor_centavos, "
                "descricao, data_vencimento, pedido_id, parcela, total_parcelas) "
                "VALUES (1, 'Devedora', 120.5, 12050, 'Sinal', '2030-01-01', 1, 1, 1)")
    con.commit()
    con.close()

    with pytest.raises(database.ClienteTemVinculos) as capturado:
        database.excluir_cliente(1)
    assert "parcela(s) a receber" in str(capturado.value)


# =============================================================================
# Migrations e fallback nao podem divergir de novo
# =============================================================================
def test_o_schema_das_migrations_e_o_do_fallback_concordam_nos_defaults(
        banco_das_migrations, tmp_path, monkeypatch):
    """
    A divergencia entre os dois caminhos foi a causa-raiz: o defeito existia so
    num deles, e os testes exercitavam justamente o outro.
    """
    caminho_fallback = tmp_path / "fallback.db"
    monkeypatch.setattr(database, "DB_PATH", str(caminho_fallback))
    database.criar_tabela()

    for tabela in ('entregas_agendadas', 'pagamentos', 'clientes'):
        das_migrations = _defaults(banco_das_migrations, tabela)
        do_fallback = _defaults(str(caminho_fallback), tabela)
        comuns = set(das_migrations) & set(do_fallback)
        divergentes = {
            coluna: (das_migrations[coluna], do_fallback[coluna])
            for coluna in comuns
            if (das_migrations[coluna] or '') != (do_fallback[coluna] or '')
        }
        assert not divergentes, f"{tabela}: DEFAULT diverge (migration, fallback) = {divergentes}"


# =============================================================================
# O beco sem saida da parcela orfa
# =============================================================================
def test_parcela_sem_pedido_e_relatada_como_nao_resolvivel_pela_interface(
        banco_das_migrations):
    """
    Parcela sem `pedido_id` nao aparece em tela nenhuma: as parcelas sao lidas
    e baixadas DENTRO do pedido que as emitiu. Antes desta mensagem o cliente
    ficava inexcluivel para sempre e o aviso mandava "conclua ou cancele" algo
    que o operador nao tinha como encontrar.

    Nenhum caminho de escrita atual produz uma linha dessas -- `inserir_parcela`
    exige o pedido e e o unico INSERT em `pagamentos`. Ela so existe em banco
    anterior a 1.5.0, do tempo do cadastro avulso de pagamento.
    """
    con = sqlite3.connect(banco_das_migrations)
    con.execute("INSERT INTO clientes (nome, cep, rua, bairro, cidade, entrega_retirada) "
                "VALUES ('Legada', '89200-000', 'R', 'B', 'Joinville', 'Entrega')")
    con.execute("INSERT INTO pagamentos (cliente_id, cliente_nome, valor, valor_centavos, "
                "descricao, data_vencimento, status) "
                "VALUES (1, 'Legada', 50.0, 5000, 'Avulso antigo', '2030-01-01', 'Pendente')")
    con.commit()
    con.close()

    with pytest.raises(database.ClienteTemVinculos) as capturado:
        database.excluir_cliente(1)

    texto = str(capturado.value)
    assert "sem pedido" in texto
    assert "suporte" in texto, "a mensagem precisa dizer que a interface nao resolve este caso"


def test_parcela_legada_marcada_como_atrasada_tambem_trava(banco_das_migrations):
    """
    O codigo atual nunca grava 'Atrasado' -- o atraso e derivado do vencimento.
    Mas versoes anteriores gravavam, e uma parcela vencida e mais devida, nao
    menos: ignora-la deixaria sair justamente a divida mais velha.
    """
    con = sqlite3.connect(banco_das_migrations)
    con.execute("INSERT INTO clientes (nome, cep, rua, bairro, cidade, entrega_retirada) "
                "VALUES ('Atrasada', '89200-000', 'R', 'B', 'Joinville', 'Entrega')")
    con.execute("INSERT INTO pedidos (numero, cliente_id, cliente_nome, data_emissao, situacao) "
                "VALUES ('PED-2026-000001', 1, 'Atrasada', '2026-01-01', 'faturado')")
    con.execute("INSERT INTO pagamentos (cliente_id, cliente_nome, valor, valor_centavos, "
                "descricao, data_vencimento, status, pedido_id, parcela, total_parcelas) "
                "VALUES (1, 'Atrasada', 50.0, 5000, 'Parcela 1/1', '2020-01-01', 'Atrasado', 1, 1, 1)")
    con.commit()
    con.close()

    with pytest.raises(database.ClienteTemVinculos) as capturado:
        database.excluir_cliente(1)
    assert "1 parcela(s) a receber" in str(capturado.value)


def test_parcela_recebida_nao_impede_a_exclusao(banco_das_migrations):
    """A trava e sobre dinheiro a entrar, nao sobre historico."""
    con = sqlite3.connect(banco_das_migrations)
    con.execute("INSERT INTO clientes (nome, cep, rua, bairro, cidade, entrega_retirada) "
                "VALUES ('Quitada', '89200-000', 'R', 'B', 'Joinville', 'Entrega')")
    con.execute("INSERT INTO pedidos (numero, cliente_id, cliente_nome, data_emissao, situacao) "
                "VALUES ('PED-2026-000001', 1, 'Quitada', '2026-01-01', 'faturado')")
    con.execute("INSERT INTO pagamentos (cliente_id, cliente_nome, valor, valor_centavos, "
                "descricao, data_vencimento, status, pedido_id, parcela, total_parcelas) "
                "VALUES (1, 'Quitada', 50.0, 5000, 'Parcela 1/1', '2026-01-01', 'Recebido', 1, 1, 1)")
    con.commit()
    con.close()

    assert database.excluir_cliente(1) == 1
