"""Track trial access separately for each local user.

Revision ID: a6c31d8f902b
Revises: f03c6a91d2e4
Create Date: 2026-10-13
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a6c31d8f902b"
down_revision: str | None = "f03c6a91d2e4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("usuarios")}
    definitions = (
        ("teste_modo", sa.Text(), "automatico"),
        ("teste_inicio_em", sa.Text(), ""),
        ("teste_ate", sa.Text(), ""),
        ("teste_controle_em", sa.Text(), ""),
    )
    for name, column_type, default in definitions:
        if name not in columns:
            op.add_column(
                "usuarios",
                sa.Column(name, column_type, nullable=False, server_default=default),
            )

    op.execute(sa.text(
        "UPDATE usuarios SET teste_modo='automatico', "
        "teste_inicio_em=strftime('%Y-%m-%dT%H:%M:%S', 'now', 'localtime'), "
        "teste_ate=strftime('%Y-%m-%dT%H:%M:%S', 'now', '+30 days', 'localtime'), "
        "teste_controle_em=strftime('%Y-%m-%dT%H:%M:%S', 'now', 'localtime') "
        "WHERE role != 'desenvolvedor' AND teste_inicio_em=''"
    ))
    op.execute(sa.text(
        "UPDATE usuarios SET teste_modo='desativado', "
        "teste_inicio_em=strftime('%Y-%m-%dT%H:%M:%S', 'now', 'localtime'), "
        "teste_ate='', "
        "teste_controle_em=strftime('%Y-%m-%dT%H:%M:%S', 'now', 'localtime') "
        "WHERE role='desenvolvedor'"
    ))


def downgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("usuarios")}
    for name in ("teste_controle_em", "teste_ate", "teste_inicio_em", "teste_modo"):
        if name in columns:
            op.drop_column("usuarios", name)
