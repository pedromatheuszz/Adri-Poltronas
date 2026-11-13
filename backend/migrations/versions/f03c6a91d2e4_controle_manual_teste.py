"""Add developer controls for the trial period.

Revision ID: f03c6a91d2e4
Revises: e41a8d6c2b90
Create Date: 2026-10-13
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f03c6a91d2e4"
down_revision: str | None = "e41a8d6c2b90"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("licenca")}
    definitions = (
        ("teste_modo", sa.Text(), ""),
        ("teste_ate", sa.Text(), ""),
        ("teste_controle_em", sa.Text(), ""),
    )
    for name, column_type, default in definitions:
        if name not in columns:
            op.add_column(
                "licenca",
                sa.Column(name, column_type, nullable=False, server_default=default),
            )


def downgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("licenca")}
    for name in ("teste_controle_em", "teste_ate", "teste_modo"):
        if name in columns:
            op.drop_column("licenca", name)
