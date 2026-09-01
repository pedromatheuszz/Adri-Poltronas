"""Testes da primeira fundacao modular do ERP."""

import json
import os
import sqlite3
import sys
from contextlib import closing

import pytest


sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

import database  # noqa: E402
import migrations_manager  # noqa: E402
from erp.core.contexto import (  # noqa: E402
    ContextoOperacao,
    encerrar_contexto,
    iniciar_contexto,
)


@pytest.fixture
def banco_fallback(tmp_path, monkeypatch):
    caminho = tmp_path / "erp.db"
    monkeypatch.setattr(database, "DB_PATH", str(caminho))
    database.criar_tabela()
    return caminho


def test_exclusao_de_cliente_e_logica_e_preserva_vinculos(banco_fallback):
    cliente_id = database.salvar_cliente(
        "Cliente", "11000-000", "Rua A", "Centro", "Santos", "Entrega"
    )
    pagamento_id = database.salvar_pagamento(
        cliente_id, "Cliente", 120.50, "Sinal", "2030-01-01"
    )

    assert database.excluir_cliente(cliente_id) == 1
    assert database.listar_clientes() == []
    assert database.obter_cliente_por_id(cliente_id) is None

    with database.conectar() as conexao:
        cliente = conexao.execute(
            "SELECT ativo, excluido_em FROM clientes WHERE id=?", (cliente_id,)
        ).fetchone()
        pagamento = conexao.execute(
            "SELECT id FROM pagamentos WHERE id=?", (pagamento_id,)
        ).fetchone()
        auditoria = conexao.execute(
            "SELECT acao FROM auditoria_eventos WHERE entidade='cliente' "
            "AND entidade_id=? ORDER BY id DESC LIMIT 1",
            (str(cliente_id),),
        ).fetchone()

    assert cliente["ativo"] == 0
    assert cliente["excluido_em"]
    assert pagamento["id"] == pagamento_id
    assert auditoria["acao"] == "crm.cliente.inativado"


def test_foreign_keys_sao_aplicadas_em_toda_conexao(banco_fallback):
    with database.conectar() as conexao:
        assert conexao.execute("PRAGMA foreign_keys").fetchone()[0] == 1

    with pytest.raises(sqlite3.IntegrityError):
        database.salvar_pagamento(
            99999, "Inexistente", 10.0, "Registro invalido", "2030-01-01"
        )


def test_falha_na_auditoria_reverte_a_operacao(banco_fallback, monkeypatch):
    def falhar_auditoria(*_args, **_kwargs):
        raise RuntimeError("auditoria indisponivel")

    monkeypatch.setattr(database, "registrar_evento", falhar_auditoria)

    with pytest.raises(RuntimeError, match="auditoria indisponivel"):
        database.salvar_cliente(
            "Nao persiste", "11000-001", "Rua", "Centro", "Santos", "Entrega"
        )

    with database.conectar() as conexao:
        assert conexao.execute("SELECT COUNT(*) FROM clientes").fetchone()[0] == 0
        assert conexao.execute("SELECT COUNT(*) FROM historico").fetchone()[0] == 0


def test_auditoria_redige_segredos_e_e_append_only(banco_fallback):
    cliente_id = database.salvar_cliente(
        "Cliente", "11000-002", "Rua", "Centro", "Santos", "Entrega"
    )
    pagamento_id = database.salvar_pagamento(
        cliente_id, "Cliente", 45.0, "Entrada", "2030-01-01"
    )
    token_contexto = iniciar_contexto(
        ContextoOperacao(
            origem="teste",
            correlation_id="corr-123",
            usuario_identificador="gestor@empresa.local",
        )
    )
    try:
        database.atualizar_pagamento(
            pagamento_id,
            pix_payload="payload-secreto",
            pix_qr_code="imagem-secreta",
            boleto_url="https://boleto.exemplo/token-secreto",
        )
    finally:
        encerrar_contexto(token_contexto)

    with database.conectar() as conexao:
        evento = conexao.execute(
            "SELECT * FROM auditoria_eventos WHERE entidade='pagamento' "
            "AND entidade_id=? ORDER BY id DESC LIMIT 1",
            (str(pagamento_id),),
        ).fetchone()
        dados_novos = json.loads(evento["valores_novos"])
        assert dados_novos["pix_payload"] == "[REDACTED]"
        assert dados_novos["pix_qr_code"] == "[REDACTED]"
        assert dados_novos["boleto_url"] == "[REDACTED]"
        assert "payload-secreto" not in evento["valores_novos"]
        assert evento["correlation_id"] == "corr-123"
        assert evento["usuario_identificador"] == "gestor@empresa.local"

        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            conexao.execute(
                "UPDATE auditoria_eventos SET acao='alterada' WHERE id=?", (evento["id"],)
            )


def test_migrations_reconstroem_schema_integral_em_banco_novo(tmp_path, monkeypatch):
    caminho = tmp_path / "migrations.db"
    monkeypatch.setattr(database, "DB_PATH", str(caminho))

    migrations_manager.aplicar_migrações()

    with closing(sqlite3.connect(caminho)) as conexao:
        revisao = conexao.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        colunas_clientes = {
            linha[1] for linha in conexao.execute("PRAGMA table_info(clientes)")
        }
        tabelas = {
            linha[0]
            for linha in conexao.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        fks_pagamentos = conexao.execute("PRAGMA foreign_key_list(pagamentos)").fetchall()
        colunas_sessao = {
            linha[1] for linha in conexao.execute("PRAGMA table_info(sessao)")
        }
        gatilhos = {
            linha[0]
            for linha in conexao.execute(
                "SELECT name FROM sqlite_master WHERE type='trigger'"
            )
        }

    # Cabeca da cadeia de migrations. Atualizar junto ao acrescentar uma
    # revisao nova -- e o que garante que ela entrou na cadeia, e nao ficou
    # pendurada fora dela.
    assert revisao == "b5a1c7e94d20"
    assert {"ativo", "excluido_em"} <= colunas_clientes
    # Sem estas duas a sessao Microsoft nao pode ser renovada e o operador
    # volta a refazer o login a cada hora para exportar uma planilha.
    assert {"refresh_token", "expira_em"} <= colunas_sessao
    assert "auditoria_eventos" in tabelas
    assert any(fk[2] == "clientes" and fk[6] == "RESTRICT" for fk in fks_pagamentos)
    assert {
        "trg_auditoria_eventos_immutable_update",
        "trg_auditoria_eventos_immutable_delete",
    } <= gatilhos

    cliente_id = database.salvar_cliente(
        "Migrado", "11000-004", "Rua", "Centro", "Santos", "Entrega"
    )
    cliente = database.obter_cliente_por_id(cliente_id)
    assert cliente["criado_em"]
    with database.conectar() as conexao:
        assert conexao.execute(
            "SELECT COUNT(*) FROM auditoria_eventos WHERE entidade_id=?",
            (str(cliente_id),),
        ).fetchone()[0] == 1


def test_webhook_financeiro_e_idempotente(banco_fallback):
    cliente_id = database.salvar_cliente(
        "Cliente", "11000-003", "Rua", "Centro", "Santos", "Entrega"
    )
    pagamento_id = database.salvar_pagamento(
        cliente_id, "Cliente", 89.0, "Parcela", "2030-01-01"
    )
    database.atualizar_pagamento(pagamento_id, asaas_payment_id="pay_123")

    assert database.atualizar_pagamento_por_asaas(
        "pay_123", "Recebido", preencher_data_pagamento=True
    ) == 1
    assert database.atualizar_pagamento_por_asaas(
        "pay_123", "Recebido", preencher_data_pagamento=True
    ) == 0

    with database.conectar() as conexao:
        historicos = conexao.execute(
            "SELECT COUNT(*) FROM historico WHERE cliente_id=? "
            "AND detalhes LIKE 'Pagamento confirmado via webhook:%'",
            (cliente_id,),
        ).fetchone()[0]
        eventos = conexao.execute(
            "SELECT COUNT(*) FROM auditoria_eventos "
            "WHERE acao='financeiro.recebivel.webhook_atualizado' "
            "AND entidade_id=?",
            (str(pagamento_id),),
        ).fetchone()[0]

    assert historicos == 1
    assert eventos == 1
