"""Guarda a resposta ASSINADA da API central de licencas.

O cache da licenca central vivia em quatro colunas de texto simples --
`licenca_remota_estado`, `_expira_em`, `_verificada_em`, `_offline_ate` -- e
o guarda de licenca acreditava nelas. Bastava um `UPDATE usuarios SET
licenca_remota_estado = 'paid', licenca_remota_offline_ate = '2999-01-01'`
para a instalacao se declarar paga para sempre.

Esta coluna guarda a prova que o servidor assina (estado, validade, conta,
instalacao e instante de emissao). Com a chave publica configurada em
`backend/licenca_remota.py`, e DELA que o estado e lido; as colunas antigas
passam a valer apenas para lembrar uma recusa, nunca para conceder acesso.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a9d4c6e18f27"
down_revision: str | None = "e8b3f7a2c1d4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

COLUNA = "licenca_remota_prova"


def _colunas() -> set:
    return {coluna["name"] for coluna in sa.inspect(op.get_bind()).get_columns("usuarios")}


def upgrade() -> None:
    if COLUNA not in _colunas():
        op.add_column("usuarios", sa.Column(COLUNA, sa.Text(), nullable=False, server_default=""))


def downgrade() -> None:
    if COLUNA in _colunas():
        op.drop_column("usuarios", COLUNA)
