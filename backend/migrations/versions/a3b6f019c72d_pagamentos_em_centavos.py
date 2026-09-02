"""pagamentos.valor_centavos e as chaves estrangeiras de pedido

DINHEIRO EM PONTO FLUTUANTE
`pagamentos.valor` e SQLite REAL, ou seja, IEEE 754 binario. Isso nao
representa 0,10 exatamente -- e num sistema financeiro o erro nao fica
escondido:

    >>> 0.1 + 0.2
    0.30000000000000004
    >>> sum([33.33, 33.33, 33.34])
    99.99999999999999

O modulo comercial ja nasceu certo: `pedidos` e `pedido_itens` guardam centavos
inteiros e `dinheiro.ratear` divide parcelas sem perder centavo. Mas o
faturamento entregava o resultado a `pagamentos`, e ali ele virava float --
`round(centavos / 100, 2)`. Tres parcelas de um pedido de R$ 100,00 eram
rateadas corretamente em 3333/3333/3334 centavos e gravadas como
33.33/33.33/33.34; somar de volta nao devolve 100,00.

Esta migration acrescenta `valor_centavos` e faz o backfill. As duas colunas
convivem por uma versao: `valor` continua sendo gravado e lido para que
qualquer consulta, relatorio ou integracao que dependa dele siga funcionando.
`valor_centavos` e a fonte de verdade a partir daqui.

CHAVES ESTRANGEIRAS DE PEDIDO
`pagamentos.pedido_id` e `entregas_agendadas.pedido_id` foram acrescentadas por
ALTER TABLE em c9f4e2a71b83, e SQLite nao aceita adicionar constraint por
ALTER. As colunas ficaram sem FK: nada impedia uma parcela apontando para um
pedido que nao existe, e apagar um pedido deixava parcelas orfas em silencio.

A recriacao usa `batch_alter_table`, o mesmo caminho de f4c8b2d6e1a0. Antes de
criar a constraint, `pedido_id` orfao vira NULL -- criar a FK com dado que a
viola faria a migration falhar no meio, que e justamente o cenario que o
backup de pre-migracao existe para cobrir e que ninguem quer exercitar.

Revision ID: a3b6f019c72d
Revises: e2a9c4d70f61
Create Date: 2026-09-01 23:30:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a3b6f019c72d"
down_revision: Union[str, None] = "e2a9c4d70f61"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Convencao de nomes: sem ela, o `batch_alter_table` nao consegue referenciar
# constraints anonimas na hora de recriar a tabela.
_NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def _colunas(tabela: str) -> set:
    inspetor = sa.inspect(op.get_bind())
    return {coluna["name"] for coluna in inspetor.get_columns(tabela)}


def _tem_fk_para_pedidos(tabela: str) -> bool:
    inspetor = sa.inspect(op.get_bind())
    return any(
        fk.get("referred_table") == "pedidos"
        for fk in inspetor.get_foreign_keys(tabela)
    )


def upgrade() -> None:
    conexao = op.get_bind()

    # ---------------------------------------------------------------- centavos
    if "valor_centavos" not in _colunas("pagamentos"):
        op.add_column("pagamentos", sa.Column("valor_centavos", sa.Integer(), nullable=True))

        # ROUND antes de CAST. `CAST(33.335 * 100 AS INTEGER)` trunca para 3333
        # em vez de arredondar para 3334 -- e um centavo perdido por linha,
        # multiplicado por toda a base, e exatamente o tipo de erro que motivou
        # a coluna.
        conexao.execute(
            sa.text(
                "UPDATE pagamentos SET valor_centavos = "
                "CAST(ROUND(COALESCE(valor, 0) * 100) AS INTEGER) "
                "WHERE valor_centavos IS NULL"
            )
        )

    # ------------------------------------------------------- FKs de pedido_id
    #
    # Orfaos viram NULL antes da constraint existir. Sao poucos ou nenhum na
    # pratica -- a coluna e recente --, mas criar FK sobre dado que a viola
    # aborta a migration no meio.
    conexao.execute(
        sa.text(
            "UPDATE pagamentos SET pedido_id = NULL WHERE pedido_id IS NOT NULL "
            "AND pedido_id NOT IN (SELECT id FROM pedidos)"
        )
    )
    conexao.execute(
        sa.text(
            "UPDATE entregas_agendadas SET pedido_id = NULL WHERE pedido_id IS NOT NULL "
            "AND pedido_id NOT IN (SELECT id FROM pedidos)"
        )
    )

    # RESTRICT, e nao CASCADE: apagar um pedido nao pode levar junto as
    # parcelas e as entregas dele. O dominio ja resolve isso por cancelamento,
    # que preserva o registro.
    if not _tem_fk_para_pedidos("pagamentos"):
        with op.batch_alter_table(
            "pagamentos", recreate="always", naming_convention=_NAMING_CONVENTION
        ) as batch:
            batch.create_foreign_key(
                "fk_pagamentos_pedido_id_pedidos",
                "pedidos", ["pedido_id"], ["id"], ondelete="RESTRICT",
            )

    if not _tem_fk_para_pedidos("entregas_agendadas"):
        with op.batch_alter_table(
            "entregas_agendadas", recreate="always", naming_convention=_NAMING_CONVENTION
        ) as batch:
            batch.create_foreign_key(
                "fk_entregas_agendadas_pedido_id_pedidos",
                "pedidos", ["pedido_id"], ["id"], ondelete="RESTRICT",
            )

    # O `recreate="always"` refaz a tabela do zero e leva junto os indices
    # declarados no modelo -- que aqui nao existem, porque este schema e
    # mantido por SQL cru. Recria-los explicitamente.
    _recriar_indices(conexao)


def _recriar_indices(conexao) -> None:
    for comando in (
        "CREATE INDEX IF NOT EXISTS ix_pagamentos_cliente_id ON pagamentos(cliente_id)",
        "CREATE INDEX IF NOT EXISTS ix_pagamentos_status_pagamento "
        "ON pagamentos(status, data_pagamento)",
        "CREATE INDEX IF NOT EXISTS ix_pagamentos_status_vencimento "
        "ON pagamentos(status, data_vencimento)",
        "CREATE INDEX IF NOT EXISTS ix_pagamentos_pedido_id ON pagamentos(pedido_id)",
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_pagamentos_asaas_payment_id "
        "ON pagamentos(asaas_payment_id) "
        "WHERE asaas_payment_id IS NOT NULL AND asaas_payment_id != ''",
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_pagamentos_asaas_external_reference "
        "ON pagamentos(asaas_external_reference) "
        "WHERE asaas_external_reference IS NOT NULL AND asaas_external_reference != ''",
        "CREATE INDEX IF NOT EXISTS ix_entregas_cliente_id "
        "ON entregas_agendadas(cliente_id)",
        "CREATE INDEX IF NOT EXISTS ix_entregas_data_status "
        "ON entregas_agendadas(data_entrega, status)",
        "CREATE INDEX IF NOT EXISTS ix_entregas_pedido_id "
        "ON entregas_agendadas(pedido_id)",
    ):
        conexao.execute(sa.text(comando))


def downgrade() -> None:
    # As FKs voltam a nao existir; a coluna de centavos sai. `valor` nunca
    # deixou de ser gravado, entao nada se perde ao descer.
    if _tem_fk_para_pedidos("entregas_agendadas"):
        with op.batch_alter_table(
            "entregas_agendadas", recreate="always", naming_convention=_NAMING_CONVENTION
        ) as batch:
            batch.drop_constraint("fk_entregas_agendadas_pedido_id_pedidos", type_="foreignkey")

    if _tem_fk_para_pedidos("pagamentos"):
        with op.batch_alter_table(
            "pagamentos", recreate="always", naming_convention=_NAMING_CONVENTION
        ) as batch:
            batch.drop_constraint("fk_pagamentos_pedido_id_pedidos", type_="foreignkey")

    if "valor_centavos" in _colunas("pagamentos"):
        op.drop_column("pagamentos", "valor_centavos")

    _recriar_indices(op.get_bind())
