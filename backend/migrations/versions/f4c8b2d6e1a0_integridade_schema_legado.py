"""Reconcilia o schema legado com a revisao instalada em producao.

Revision ID: f4c8b2d6e1a0
Revises: 7c2f19a4b8e3
Create Date: 2026-08-29 10:00:00.000000

Esta revisao foi recuperada a partir do schema SQLite instalado. Bancos ja
marcados em ``f4c8b2d6e1a0`` nao a executam novamente; bancos novos passam a
receber a mesma estrutura antes das proximas evolucoes.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f4c8b2d6e1a0"
down_revision: Union[str, None] = "7c2f19a4b8e3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_NAMING_CONVENTION = {
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
}
_AGORA_LOCAL = sa.text("(datetime('now', 'localtime'))")


def upgrade() -> None:
    with op.batch_alter_table("clientes", recreate="always") as batch:
        batch.alter_column(
            "entrega_retirada",
            existing_type=sa.Text(),
            existing_nullable=False,
            server_default=sa.text("'Entrega'"),
        )
        batch.alter_column(
            "observacoes",
            existing_type=sa.Text(),
            existing_nullable=True,
            server_default=sa.text("''"),
        )
        batch.alter_column(
            "criado_em",
            existing_type=sa.Text(),
            existing_nullable=True,
            server_default=_AGORA_LOCAL,
        )
        batch.alter_column(
            "atualizado_em",
            existing_type=sa.Text(),
            existing_nullable=True,
            server_default=_AGORA_LOCAL,
        )
        batch.add_column(
            sa.Column("ativo", sa.Integer(), nullable=False, server_default=sa.text("1"))
        )
        batch.add_column(
            sa.Column("excluido_em", sa.Text(), nullable=True, server_default=sa.text("''"))
        )

    with op.batch_alter_table(
        "historico", recreate="always", naming_convention=_NAMING_CONVENTION
    ) as batch:
        batch.alter_column(
            "detalhes",
            existing_type=sa.Text(),
            existing_nullable=True,
            server_default=sa.text("''"),
        )
        batch.alter_column(
            "data_hora",
            existing_type=sa.Text(),
            existing_nullable=True,
            server_default=_AGORA_LOCAL,
        )
        batch.create_foreign_key(
            "fk_historico_cliente_id_clientes",
            "clientes",
            ["cliente_id"],
            ["id"],
            ondelete="SET NULL",
        )

    with op.batch_alter_table(
        "pagamentos", recreate="always", naming_convention=_NAMING_CONVENTION
    ) as batch:
        batch.alter_column(
            "criado_em",
            existing_type=sa.Text(),
            existing_nullable=True,
            server_default=_AGORA_LOCAL,
        )
        batch.add_column(
            sa.Column(
                "asaas_external_reference", sa.Text(), nullable=True, server_default=sa.text("''")
            )
        )
        batch.add_column(
            sa.Column("asaas_emissao_estado", sa.Text(), nullable=True, server_default=sa.text("''"))
        )
        batch.add_column(
            sa.Column("asaas_emissao_inicio", sa.Text(), nullable=True, server_default=sa.text("''"))
        )
        batch.create_foreign_key(
            "fk_pagamentos_cliente_id_clientes",
            "clientes",
            ["cliente_id"],
            ["id"],
            ondelete="RESTRICT",
        )

    with op.batch_alter_table(
        "clientes_asaas", recreate="always", naming_convention=_NAMING_CONVENTION
    ) as batch:
        batch.add_column(
            sa.Column(
                "asaas_external_reference", sa.Text(), nullable=True, server_default=sa.text("''")
            )
        )
        batch.add_column(
            sa.Column("asaas_criacao_estado", sa.Text(), nullable=True, server_default=sa.text("''"))
        )
        batch.add_column(
            sa.Column("asaas_criacao_inicio", sa.Text(), nullable=True, server_default=sa.text("''"))
        )
        batch.create_foreign_key(
            "fk_clientes_asaas_cliente_id_clientes",
            "clientes",
            ["cliente_id"],
            ["id"],
            ondelete="RESTRICT",
        )

    with op.batch_alter_table(
        "entregas_agendadas", recreate="always", naming_convention=_NAMING_CONVENTION
    ) as batch:
        batch.alter_column(
            "criado_em",
            existing_type=sa.Text(),
            existing_nullable=True,
            server_default=_AGORA_LOCAL,
        )
        batch.create_foreign_key(
            "fk_entregas_agendadas_cliente_id_clientes",
            "clientes",
            ["cliente_id"],
            ["id"],
            ondelete="RESTRICT",
        )

    op.execute("CREATE INDEX ix_clientes_id ON clientes(id DESC)")
    op.create_index("ix_clientes_nome_cep", "clientes", ["nome", "cep"])
    op.create_index("ix_clientes_criado_em", "clientes", ["criado_em"])
    op.create_index(
        "ix_clientes_ativo_atualizado_em", "clientes", ["ativo", "atualizado_em"]
    )
    op.create_index("ix_historico_cliente_id", "historico", ["cliente_id"])
    op.create_index("ix_historico_data_hora", "historico", ["data_hora"])
    op.create_index("ix_pagamentos_cliente_id", "pagamentos", ["cliente_id"])
    op.create_index(
        "ix_pagamentos_status_pagamento", "pagamentos", ["status", "data_pagamento"]
    )
    op.create_index(
        "ix_pagamentos_status_vencimento", "pagamentos", ["status", "data_vencimento"]
    )
    op.create_index("ix_entregas_cliente_id", "entregas_agendadas", ["cliente_id"])
    op.create_index(
        "ix_entregas_data_status", "entregas_agendadas", ["data_entrega", "status"]
    )

    op.create_index(
        "ux_pagamentos_asaas_payment_id",
        "pagamentos",
        ["asaas_payment_id"],
        unique=True,
        sqlite_where=sa.text("asaas_payment_id IS NOT NULL AND asaas_payment_id != ''"),
    )
    op.create_index(
        "ux_pagamentos_asaas_external_reference",
        "pagamentos",
        ["asaas_external_reference"],
        unique=True,
        sqlite_where=sa.text(
            "asaas_external_reference IS NOT NULL AND asaas_external_reference != ''"
        ),
    )
    op.create_index(
        "ux_clientes_asaas_customer_id",
        "clientes_asaas",
        ["asaas_customer_id"],
        unique=True,
        sqlite_where=sa.text("asaas_customer_id IS NOT NULL AND asaas_customer_id != ''"),
    )
    op.create_index(
        "ux_clientes_asaas_external_reference",
        "clientes_asaas",
        ["asaas_external_reference"],
        unique=True,
        sqlite_where=sa.text(
            "asaas_external_reference IS NOT NULL AND asaas_external_reference != ''"
        ),
    )


def downgrade() -> None:
    for tabela, indice in [
        ("clientes_asaas", "ux_clientes_asaas_external_reference"),
        ("clientes_asaas", "ux_clientes_asaas_customer_id"),
        ("pagamentos", "ux_pagamentos_asaas_external_reference"),
        ("pagamentos", "ux_pagamentos_asaas_payment_id"),
        ("entregas_agendadas", "ix_entregas_data_status"),
        ("entregas_agendadas", "ix_entregas_cliente_id"),
        ("pagamentos", "ix_pagamentos_status_vencimento"),
        ("pagamentos", "ix_pagamentos_status_pagamento"),
        ("pagamentos", "ix_pagamentos_cliente_id"),
        ("historico", "ix_historico_data_hora"),
        ("historico", "ix_historico_cliente_id"),
        ("clientes", "ix_clientes_ativo_atualizado_em"),
        ("clientes", "ix_clientes_criado_em"),
        ("clientes", "ix_clientes_nome_cep"),
        ("clientes", "ix_clientes_id"),
    ]:
        op.drop_index(indice, table_name=tabela)

    with op.batch_alter_table(
        "entregas_agendadas", recreate="always", naming_convention=_NAMING_CONVENTION
    ) as batch:
        batch.drop_constraint("fk_entregas_agendadas_cliente_id_clientes", type_="foreignkey")
        batch.alter_column("criado_em", existing_type=sa.Text(), server_default=None)

    with op.batch_alter_table(
        "clientes_asaas", recreate="always", naming_convention=_NAMING_CONVENTION
    ) as batch:
        batch.drop_constraint("fk_clientes_asaas_cliente_id_clientes", type_="foreignkey")
        batch.drop_column("asaas_criacao_inicio")
        batch.drop_column("asaas_criacao_estado")
        batch.drop_column("asaas_external_reference")

    with op.batch_alter_table(
        "pagamentos", recreate="always", naming_convention=_NAMING_CONVENTION
    ) as batch:
        batch.drop_constraint("fk_pagamentos_cliente_id_clientes", type_="foreignkey")
        batch.drop_column("asaas_emissao_inicio")
        batch.drop_column("asaas_emissao_estado")
        batch.drop_column("asaas_external_reference")
        batch.alter_column("criado_em", existing_type=sa.Text(), server_default=None)

    with op.batch_alter_table(
        "historico", recreate="always", naming_convention=_NAMING_CONVENTION
    ) as batch:
        batch.drop_constraint("fk_historico_cliente_id_clientes", type_="foreignkey")
        batch.alter_column("data_hora", existing_type=sa.Text(), server_default=None)

    with op.batch_alter_table("clientes", recreate="always") as batch:
        batch.drop_column("excluido_em")
        batch.drop_column("ativo")
        batch.alter_column("atualizado_em", existing_type=sa.Text(), server_default=None)
        batch.alter_column("criado_em", existing_type=sa.Text(), server_default=None)
