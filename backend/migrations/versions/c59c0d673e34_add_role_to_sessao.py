"""add_role_to_sessao

Revision ID: c59c0d673e34
Revises: b7f21c9e4a05
Create Date: 2026-10-13 02:21:01.275648

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c59c0d673e34'
down_revision: str | None = 'b7f21c9e4a05'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('sessao', sa.Column('role', sa.Text(), nullable=False, server_default='usuario'))


def downgrade() -> None:
    op.drop_column('sessao', 'role')
