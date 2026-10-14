"""add_local_auth_columns

Revision ID: 31f5f545e0a5
Revises: c59c0d673e34
Create Date: 2026-10-13 02:32:00.035755

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '31f5f545e0a5'
down_revision: str | None = 'c59c0d673e34'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Tabela usuarios
    op.create_table(
        'usuarios',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('username', sa.Text(), nullable=False, unique=True),
        sa.Column('email', sa.Text(), nullable=True),
        sa.Column('password_hash', sa.Text(), nullable=False),
        sa.Column('role', sa.Text(), nullable=False, server_default='usuario'),
        sa.Column('ativo', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('criado_em', sa.Text(), nullable=False, server_default="(datetime('now', 'localtime'))"),
        sa.Column('atualizado_em', sa.Text(), nullable=False, server_default="(datetime('now', 'localtime'))"),
        sa.Column('ultimo_login_em', sa.Text(), nullable=True),
    )
    op.create_index('ix_usuarios_username', 'usuarios', ['username'])
    op.create_index('ix_usuarios_email', 'usuarios', ['email'])

    # Colunas na sessao para auth local
    op.add_column('sessao', sa.Column('user_id', sa.Integer(), nullable=True))
    op.add_column('sessao', sa.Column('tipo', sa.Text(), nullable=False, server_default='microsoft'))


def downgrade() -> None:
    op.drop_column('sessao', 'tipo')
    op.drop_column('sessao', 'user_id')
    op.drop_table('usuarios')
