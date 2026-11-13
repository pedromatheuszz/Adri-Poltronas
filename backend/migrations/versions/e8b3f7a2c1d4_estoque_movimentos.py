"""Estoque: movimentos de entrada e saida por produto

Ate aqui a aba Produtos era so catalogo, e o README dizia isso com todas as
letras: nao havia quantidade total, nao havia disponivel, nao havia locado.
O operador conferia a disponibilidade fisica da poltrona por telefone antes
de aprovar a locacao -- o sistema nao tinha como ajudar.

O desenho escolhido e o mais curto que fecha o ciclo:

* `estoque_movimentos` e o livro-razao do estoque. Nenhuma coluna de
  quantidade em `produtos`: o total e SEMPRE a soma dos movimentos, e
  corrigir um erro de contagem e lancar o ajuste, nao reescrever o
  presente. Movimento nao se apaga pelo mesmo motivo que auditoria nao se
  apaga: o historico e o que permite explicar por que o total e o que e.
* A RESERVA nao e tabela. Ela e derivada dos proprios pedidos: itens de
  pedidos aprovados e faturados, com janela de aluguel, sao poltronas que
  nao podem ser prometidas duas vezes para o mesmo periodo. Rascunho e
  aberto nao reservam -- negociacao em andamento nao e compromisso --, mas
  aparecem como "em negociacao" para o operador ver a disputa antes que
  ela vire problema.

Aditiva como as anteriores: nenhuma tabela existente muda.

Revision ID: e8b3f7a2c1d4
Revises: f2d71a9c0b64
Create Date: 2026-09-15 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e8b3f7a2c1d4"
down_revision: str | None = "f2d71a9c0b64"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

AGORA = sa.text("(datetime('now', 'localtime'))")


def _tabelas() -> set:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    if "estoque_movimentos" in _tabelas():
        return

    op.create_table(
        "estoque_movimentos",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("produto_id", sa.Integer(), nullable=False),
        # Positivo entra (aquisicao, ajuste para cima), negativo sai (baixa
        # por avaria, manutencao longa, ajuste para baixo). Um movimento de
        # delta zero nao diz nada e nao existe.
        sa.Column("delta", sa.Integer(), nullable=False),
        # O tipo orienta a tela e o relatorio; o sinal e conferido na borda,
        # no servico -- CHECK aqui cobriria so o caso honesto do proprio
        # backend escrevendo certo.
        sa.Column(
            "tipo",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'ajuste'"),
        ),
        sa.Column("motivo", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("criado_em", sa.Text(), nullable=False, server_default=AGORA),
        sa.PrimaryKeyConstraint("id"),
        # RESTRICT: apagar um produto que tem movimentos apagaria o razao
        # dele. O catalogo ja inativa em vez de apagar; a FK e a rede de
        # seguranca.
        sa.ForeignKeyConstraint(
            ["produto_id"],
            ["produtos.id"],
            name="fk_estoque_movimentos_produto_id_produtos",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("delta != 0", name="ck_estoque_movimentos_delta_nao_nulo"),
        sa.CheckConstraint(
            "tipo IN ('aquisicao', 'baixa', 'ajuste')",
            name="ck_estoque_movimentos_tipo",
        ),
    )
    op.create_index(
        "ix_estoque_movimentos_produto_id", "estoque_movimentos", ["produto_id"]
    )
    op.create_index(
        "ix_estoque_movimentos_criado_em", "estoque_movimentos", ["criado_em"]
    )


def downgrade() -> None:
    if "estoque_movimentos" in _tabelas():
        op.drop_table("estoque_movimentos")
