"""Reserva e impressao do corpo nas operacoes idempotentes

O QUE FALTAVA
A primeira versao registrava a chave DEPOIS de executar a escrita, em outra
transacao. A janela entre as duas e pequena e real: um processo encerrado ali
deixa a escrita feita e a chave sem registro, e a fila offline reenvia -- que
e exatamente o que a chave existe para impedir.

Nao da para juntar as duas numa transacao so sem reescrever todas as rotas
para receberem a conexao de fora. A saida e a mesma que o modulo de emissao
usa: registrar a INTENCAO antes de agir.

    reserva  ->  executa  ->  conclui

Cair entre a reserva e a execucao deixa a chave reservada e nada escrito: a
repeticao ve "em andamento" e recua. Cair entre a execucao e a conclusao
deixa a escrita feita e a chave reservada: a repeticao tambem recua, e nao
duplica. Em nenhum dos dois casos a operacao acontece duas vezes, que e a
propriedade que importa.

`impressao` guarda um hash de metodo + rota + corpo. Sem ele, reaproveitar a
mesma chave para outra operacao devolveria em silencio a resposta da primeira
-- um erro de cliente que viraria dado errado sem nenhum sinal.

Revision ID: c4d81a5f9e37
Revises: a3b6f019c72d
Create Date: 2026-09-02 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c4d81a5f9e37"
down_revision: str | None = "a3b6f019c72d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ESTADO_CONCLUIDA = "concluida"


def _colunas(tabela: str) -> set:
    inspetor = sa.inspect(op.get_bind())
    return {coluna["name"] for coluna in inspetor.get_columns(tabela)}


def upgrade() -> None:
    conexao = op.get_bind()
    colunas = _colunas("operacoes_idempotentes")

    if "estado" not in colunas:
        op.add_column(
            "operacoes_idempotentes",
            sa.Column("estado", sa.Text(), nullable=False,
                      server_default=sa.text(f"'{ESTADO_CONCLUIDA}'")),
        )
        # As linhas que ja existem sao, por construcao, respostas concluidas:
        # a versao anterior so gravava depois de a rota responder.
        conexao.execute(
            sa.text("UPDATE operacoes_idempotentes SET estado = :estado"),
            {"estado": ESTADO_CONCLUIDA},
        )

    if "impressao" not in colunas:
        # Anulavel: as linhas antigas nao tem como saber qual era o corpo, e
        # inventar uma impressao para elas seria pior que admitir a ausencia.
        # Quem le trata `NULL` como "nao da para conferir" e segue.
        op.add_column("operacoes_idempotentes", sa.Column("impressao", sa.Text(), nullable=True))

    # `status` e `corpo` passam a ser anulaveis: uma chave RESERVADA ainda nao
    # tem resposta. SQLite nao afrouxa NOT NULL por ALTER, entao a tabela e
    # recriada.
    if _precisa_afrouxar_not_null():
        with op.batch_alter_table("operacoes_idempotentes", recreate="always") as batch:
            batch.alter_column("status", existing_type=sa.Integer(), nullable=True)
            batch.alter_column("corpo", existing_type=sa.Text(), nullable=True)
        conexao.execute(
            sa.text(
                "CREATE INDEX IF NOT EXISTS ix_operacoes_idempotentes_criado_em "
                "ON operacoes_idempotentes(criado_em)"
            )
        )


def _precisa_afrouxar_not_null() -> bool:
    inspetor = sa.inspect(op.get_bind())
    for coluna in inspetor.get_columns("operacoes_idempotentes"):
        if coluna["name"] in ("status", "corpo") and not coluna["nullable"]:
            return True
    return False


def downgrade() -> None:
    conexao = op.get_bind()
    # Reservas nunca concluidas nao tem resposta para guardar; some com elas
    # antes de restaurar o NOT NULL.
    conexao.execute(
        sa.text("DELETE FROM operacoes_idempotentes WHERE status IS NULL OR corpo IS NULL")
    )
    with op.batch_alter_table("operacoes_idempotentes", recreate="always") as batch:
        batch.alter_column("status", existing_type=sa.Integer(), nullable=False)
        batch.alter_column("corpo", existing_type=sa.Text(), nullable=False)
        batch.drop_column("impressao")
        batch.drop_column("estado")
    conexao.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS ix_operacoes_idempotentes_criado_em "
            "ON operacoes_idempotentes(criado_em)"
        )
    )
