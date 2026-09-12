"""Estado de leitura das notificacoes

Revision ID: 7c2f19a4b8e3
Revises: 21d8d4eb2b6f
Create Date: 2026-08-07 23:05:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = '7c2f19a4b8e3'
down_revision: str | None = '21d8d4eb2b6f'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # As notificacoes sao derivadas de consultas e nao ficam armazenadas; esta
    # tabela guarda apenas quais delas o usuario ja marcou como lidas, pela
    # chave estavel `tipo:id_da_entidade`.
    op.create_table(
        'notificacoes_lidas',
        sa.Column('chave', sa.Text(), nullable=False),
        sa.Column('lida_em', sa.Text(), nullable=True,
                  server_default=sa.text("(datetime('now', 'localtime'))")),
        sa.PrimaryKeyConstraint('chave'),
    )


def downgrade() -> None:
    op.drop_table('notificacoes_lidas')
