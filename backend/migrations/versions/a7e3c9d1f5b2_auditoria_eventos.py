"""Adiciona ledger imutavel de auditoria.

Revision ID: a7e3c9d1f5b2
Revises: f4c8b2d6e1a0
Create Date: 2026-08-29 10:30:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "a7e3c9d1f5b2"
down_revision: str | None = "f4c8b2d6e1a0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "auditoria_eventos",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("usuario_id", sa.Text(), nullable=True),
        sa.Column("usuario_identificador", sa.Text(), nullable=True),
        sa.Column("acao", sa.Text(), nullable=False),
        sa.Column("entidade", sa.Text(), nullable=False),
        sa.Column("entidade_id", sa.Text(), nullable=True),
        sa.Column("valores_anteriores", sa.Text(), nullable=True),
        sa.Column("valores_novos", sa.Text(), nullable=True),
        sa.Column("origem", sa.Text(), nullable=False, server_default=sa.text("'backend'")),
        sa.Column("contexto", sa.Text(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("correlation_id", sa.Text(), nullable=True),
        sa.Column(
            "criado_em",
            sa.Text(),
            nullable=False,
            server_default=sa.text("(datetime('now', 'localtime'))"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_auditoria_entidade_registro",
        "auditoria_eventos",
        ["entidade", "entidade_id", "id"],
    )
    op.create_index("ix_auditoria_criado_em", "auditoria_eventos", ["criado_em"])
    op.create_index(
        "ix_auditoria_usuario_criado_em",
        "auditoria_eventos",
        ["usuario_id", "criado_em"],
    )
    op.execute(
        """
        CREATE TRIGGER trg_auditoria_eventos_immutable_update
        BEFORE UPDATE ON auditoria_eventos
        BEGIN
            SELECT RAISE(ABORT, 'auditoria_eventos e append-only');
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_auditoria_eventos_immutable_delete
        BEFORE DELETE ON auditoria_eventos
        BEGIN
            SELECT RAISE(ABORT, 'auditoria_eventos e append-only');
        END
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_auditoria_eventos_immutable_delete")
    op.execute("DROP TRIGGER IF EXISTS trg_auditoria_eventos_immutable_update")
    op.drop_index("ix_auditoria_usuario_criado_em", table_name="auditoria_eventos")
    op.drop_index("ix_auditoria_criado_em", table_name="auditoria_eventos")
    op.drop_index("ix_auditoria_entidade_registro", table_name="auditoria_eventos")
    op.drop_table("auditoria_eventos")
