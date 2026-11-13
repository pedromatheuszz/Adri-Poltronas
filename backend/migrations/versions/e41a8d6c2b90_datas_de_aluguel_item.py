"""Persist rental period on order items.

Revision ID: e41a8d6c2b90
Revises: 31f5f545e0a5
Create Date: 2026-10-13
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e41a8d6c2b90"
down_revision: str | None = "31f5f545e0a5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("pedido_itens")}
    if "data_inicio_aluguel" not in columns:
        op.add_column("pedido_itens", sa.Column("data_inicio_aluguel", sa.Text(), nullable=False, server_default=""))
    if "data_fim_aluguel" not in columns:
        op.add_column("pedido_itens", sa.Column("data_fim_aluguel", sa.Text(), nullable=False, server_default=""))


def downgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("pedido_itens")}
    if "data_fim_aluguel" in columns:
        op.drop_column("pedido_itens", "data_fim_aluguel")
    if "data_inicio_aluguel" in columns:
        op.drop_column("pedido_itens", "data_inicio_aluguel")
