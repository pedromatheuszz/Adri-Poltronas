"""sessao guarda refresh_token e validade do access_token

A sessao Microsoft guardava apenas o access_token, que a Microsoft emite com
validade de cerca de uma hora. Sem refresh_token, passada essa hora o unico
caminho era refazer o login inteiro no navegador; e sem a validade gravada,
`/api/auth/status` respondia "logado" para um token ja morto, entao a tela
mostrava "Conectado" e o envio da planilha so falhava no clique.

Revision ID: b5a1c7e94d20
Revises: a7e3c9d1f5b2
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b5a1c7e94d20"
down_revision: str | None = "a7e3c9d1f5b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _colunas(nome_tabela: str) -> set:
    inspetor = sa.inspect(op.get_bind())
    return {coluna["name"] for coluna in inspetor.get_columns(nome_tabela)}


def upgrade() -> None:
    existentes = _colunas("sessao")

    # As duas colunas nascem anulaveis: uma instalacao que ja tem sessao
    # gravada continua com a linha antiga valida, e ela e substituida no
    # proximo login -- que ja vem com refresh_token.
    if "refresh_token" not in existentes:
        op.add_column("sessao", sa.Column("refresh_token", sa.Text(), nullable=True))
    if "expira_em" not in existentes:
        # Epoch unix em segundos. Inteiro, e nao texto ISO, porque a unica
        # operacao feita sobre ele e a comparacao com time.time().
        op.add_column("sessao", sa.Column("expira_em", sa.Integer(), nullable=True))


def downgrade() -> None:
    existentes = _colunas("sessao")
    if "expira_em" in existentes:
        op.drop_column("sessao", "expira_em")
    if "refresh_token" in existentes:
        op.drop_column("sessao", "refresh_token")
