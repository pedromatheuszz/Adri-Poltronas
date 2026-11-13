"""Add per-account identity and central license cache fields."""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f2d71a9c0b64"
down_revision: str | None = "b8f04e21c7aa"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("usuarios")}
    for name in (
        "licenca_remota_id",
        "licenca_remota_segredo",
        "licenca_remota_estado",
        "licenca_remota_expira_em",
        "licenca_remota_verificada_em",
        "licenca_remota_offline_ate",
    ):
        if name not in columns:
            op.add_column("usuarios", sa.Column(name, sa.Text(), nullable=False, server_default=""))


def downgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("usuarios")}
    for name in (
        "licenca_remota_offline_ate",
        "licenca_remota_verificada_em",
        "licenca_remota_expira_em",
        "licenca_remota_estado",
        "licenca_remota_segredo",
        "licenca_remota_id",
    ):
        if name in columns:
            op.drop_column("usuarios", name)
