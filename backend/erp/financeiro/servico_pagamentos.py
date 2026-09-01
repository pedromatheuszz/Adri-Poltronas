"""Operacoes financeiras que ultrapassam o CRUD de pagamentos."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
import sqlite3

from erp.core.auditoria import registrar_evento


FabricaConexao = Callable[[], AbstractContextManager[sqlite3.Connection]]


def aplicar_evento_asaas(
    conectar: FabricaConexao,
    asaas_payment_id: str,
    novo_status: str,
    *,
    preencher_data_pagamento: bool = False,
    status_anterior: str | None = None,
) -> int:
    """Aplica uma transicao externa de forma idempotente e auditada."""
    with conectar() as conexao:
        antigo = conexao.execute(
            "SELECT * FROM pagamentos WHERE asaas_payment_id=?", (asaas_payment_id,)
        ).fetchone()
        if not antigo or antigo["status"] == novo_status:
            return 0
        if status_anterior and antigo["status"] != status_anterior:
            return 0

        if preencher_data_pagamento:
            cursor = conexao.execute(
                "UPDATE pagamentos SET status=?, "
                "data_pagamento=datetime('now', 'localtime') "
                "WHERE asaas_payment_id=?",
                (novo_status, asaas_payment_id),
            )
        else:
            cursor = conexao.execute(
                "UPDATE pagamentos SET status=? WHERE asaas_payment_id=?",
                (novo_status, asaas_payment_id),
            )
        if cursor.rowcount == 0:
            return 0

        novo = conexao.execute(
            "SELECT * FROM pagamentos WHERE asaas_payment_id=?", (asaas_payment_id,)
        ).fetchone()
        if novo_status == "Recebido":
            conexao.execute(
                "INSERT INTO historico (cliente_id, cliente_nome, acao, detalhes) "
                "VALUES (?, ?, ?, ?)",
                (
                    antigo["cliente_id"],
                    antigo["cliente_nome"],
                    "PAGAMENTO",
                    f'Pagamento confirmado via webhook: R$ {antigo["valor"]:.2f}',
                ),
            )
        registrar_evento(
            conexao,
            acao="financeiro.recebivel.webhook_atualizado",
            entidade="pagamento",
            entidade_id=antigo["id"],
            valores_anteriores=antigo,
            valores_novos=novo,
            contexto_extra={"evento_externo": "asaas"},
        )
        return cursor.rowcount

