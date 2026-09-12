"""Lembranca das escritas ja processadas, para a fila offline poder repetir

POR QUE
A fila offline reenvia uma operacao sempre que a anterior nao confirmou. Mas
"nao confirmou" e ambiguo: o servidor pode nunca ter recebido, ou ter recebido,
gravado, e a resposta ter se perdido no caminho de volta. Do lado do navegador
as duas situacoes sao o mesmo `fetch` que rejeita.

Sem nada que distinga uma da outra, reenviar um POST de criacao produzia DOIS
clientes iguais no banco -- e o operador so descobria olhando a lista.

Com esta tabela, quem envia carrega uma chave unica por operacao e o servidor
guarda a resposta que deu para ela. A chave que volta recebe a MESMA resposta,
sem executar de novo. E o mecanismo que gateways de pagamento usam, pelo mesmo
motivo: numa rede nao confiavel, a unica forma de repetir com seguranca e o
servidor lembrar do que ja fez.

So respostas de sucesso sao registradas. Um 400 de validacao nao precisa ser
lembrado -- reenviar produz o mesmo 400, sem efeito colateral -- e guardar
erros faria a tabela crescer com o que nao interessa.

Revision ID: e2a9c4d70f61
Revises: d1e7b3f5620a
Create Date: 2026-09-01 22:40:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e2a9c4d70f61"
down_revision: str | None = "d1e7b3f5620a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _tabelas() -> set:
    inspetor = sa.inspect(op.get_bind())
    return set(inspetor.get_table_names())


def upgrade() -> None:
    if "operacoes_idempotentes" in _tabelas():
        return

    op.create_table(
        "operacoes_idempotentes",
        # A chave e o identificador da OPERACAO, gerado uma vez no momento em
        # que ela entra na fila -- nao a cada tentativa de envio. E isso que
        # faz a repeticao ser reconhecivel.
        sa.Column("chave", sa.Text(), primary_key=True),
        sa.Column("rota", sa.Text(), nullable=False),
        sa.Column("metodo", sa.Text(), nullable=False),
        sa.Column("status", sa.Integer(), nullable=False),
        # A resposta inteira, em JSON. Guardar so o status nao bastaria: a
        # repeticao precisa receber o mesmo corpo, com o mesmo id de cliente
        # criado, senao o cliente offline nao consegue remapear a fila.
        sa.Column("corpo", sa.Text(), nullable=False),
        sa.Column(
            "criado_em",
            sa.Text(),
            nullable=False,
            server_default=sa.text("(datetime('now', 'localtime'))"),
        ),
    )
    # A limpeza por idade varre esta coluna no boot.
    op.create_index(
        "ix_operacoes_idempotentes_criado_em",
        "operacoes_idempotentes",
        ["criado_em"],
    )


def downgrade() -> None:
    if "operacoes_idempotentes" not in _tabelas():
        return
    op.drop_index(
        "ix_operacoes_idempotentes_criado_em", table_name="operacoes_idempotentes"
    )
    op.drop_table("operacoes_idempotentes")
