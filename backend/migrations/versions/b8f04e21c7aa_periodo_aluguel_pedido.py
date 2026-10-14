"""Add yearless rental period to order headers.

Revision ID: b8f04e21c7aa
Revises: a6c31d8f902b
Create Date: 2026-10-13
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b8f04e21c7aa"
down_revision: str | None = "a6c31d8f902b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("pedidos")}
    for name in ("data_inicio_aluguel", "data_fim_aluguel"):
        if name not in columns:
            op.add_column(
                "pedidos",
                sa.Column(name, sa.Text(), nullable=False, server_default=""),
            )


def downgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("pedidos")}
    for name in ("data_fim_aluguel", "data_inicio_aluguel"):
        if name in columns:
            op.drop_column("pedidos", name)
