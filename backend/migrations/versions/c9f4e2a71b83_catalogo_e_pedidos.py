"""Catalogo de produtos, pedido de venda e os vinculos com entrega e pagamento

Ate aqui o sistema nao registrava O QUE foi vendido: pagamentos e entregas
ficavam pendurados direto no cliente. Sem pedido, o dashboard nao tinha receita
real, o recebimento nao sabia a que venda pertencia, e a entrega era um
compromisso de texto livre.

Quatro mudancas, todas aditivas -- nenhuma coluna existente muda de tipo ou
some, entao uma instalacao em producao sobe sem perder nada:

1. `produtos`      -- pre-requisito: nao ha item de pedido sem produto
2. `pedidos` + `pedido_itens`
3. `entregas_agendadas.pedido_id`  -- coluna na tabela que ja existe, para
   preservar as rotas e as 3 notificacoes que dependem dela
4. `pagamentos.pedido_id/parcela/total_parcelas` -- o faturamento gera N
   linhas de pagamentos, reusando toda a maquina Asaas ja funcionando

DINHEIRO
As tabelas novas usam INTEGER de centavos. `pagamentos.valor` continua REAL:
converte-la exige leitura dupla por uma versao de compatibilidade e
reconciliacao dos totais, o que e projeto proprio. A conversao acontece na
fronteira, em `erp/core/dinheiro.py`.

Revision ID: c9f4e2a71b83
Revises: b5a1c7e94d20
Create Date: 2026-09-01 14:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c9f4e2a71b83"
down_revision: str | None = "b5a1c7e94d20"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


AGORA = sa.text("(datetime('now', 'localtime'))")


def _colunas(tabela: str) -> set:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(tabela)}


def _tabelas() -> set:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    tabelas = _tabelas()

    # -----------------------------------------------------------------------
    # 1. Catalogo
    # -----------------------------------------------------------------------
    if "produtos" not in tabelas:
        op.create_table(
            "produtos",
            sa.Column("id", sa.Integer(), nullable=False),
            # Codigo interno do modelo. Unico entre os ativos, mas nao a chave:
            # renomear codigo nao pode reescrever pedido ja emitido.
            sa.Column("codigo", sa.Text(), nullable=False),
            sa.Column("descricao", sa.Text(), nullable=False),
            sa.Column("unidade", sa.Text(), nullable=False, server_default=sa.text("'un'")),
            sa.Column(
                "preco_venda_centavos", sa.Integer(), nullable=False, server_default=sa.text("0")
            ),
            sa.Column("observacoes", sa.Text(), nullable=False, server_default=sa.text("''")),
            sa.Column("ativo", sa.Integer(), nullable=False, server_default=sa.text("1")),
            sa.Column("criado_em", sa.Text(), nullable=False, server_default=AGORA),
            sa.Column("atualizado_em", sa.Text(), nullable=False, server_default=AGORA),
            sa.PrimaryKeyConstraint("id"),
            sa.CheckConstraint("preco_venda_centavos >= 0", name="ck_produtos_preco_nao_negativo"),
            sa.CheckConstraint("ativo IN (0, 1)", name="ck_produtos_ativo_booleano"),
        )
        # Parcial: um produto inativado libera o codigo para ser reusado.
        op.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS ux_produtos_codigo "
            "ON produtos(codigo) WHERE ativo = 1"
        )
        op.create_index("ix_produtos_descricao", "produtos", ["descricao"])

    # -----------------------------------------------------------------------
    # 2. Pedido de venda
    # -----------------------------------------------------------------------
    if "pedidos" not in tabelas:
        op.create_table(
            "pedidos",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("numero", sa.Text(), nullable=False),
            sa.Column("cliente_id", sa.Integer(), nullable=False),
            # Desnormalizado, como em pagamentos e entregas: o pedido impresso
            # guarda o nome do cliente no momento da emissao.
            sa.Column("cliente_nome", sa.Text(), nullable=False, server_default=sa.text("''")),
            sa.Column(
                "situacao", sa.Text(), nullable=False, server_default=sa.text("'rascunho'")
            ),
            sa.Column(
                "data_emissao",
                sa.Text(),
                nullable=False,
                server_default=sa.text("(date('now', 'localtime'))"),
            ),
            # O prazo da encomenda. E o campo que a fabricacao sob encomenda
            # exige e que hoje nao existe em lugar nenhum do sistema.
            sa.Column(
                "data_entrega_prevista", sa.Text(), nullable=False, server_default=sa.text("''")
            ),
            # Totais GRAVADOS: o valor de um pedido fechado nao pode mudar so
            # porque alguem editou o preco do produto no catalogo depois.
            sa.Column(
                "total_bruto_centavos", sa.Integer(), nullable=False, server_default=sa.text("0")
            ),
            sa.Column(
                "desconto_centavos", sa.Integer(), nullable=False, server_default=sa.text("0")
            ),
            sa.Column(
                "frete_centavos", sa.Integer(), nullable=False, server_default=sa.text("0")
            ),
            sa.Column(
                "total_liquido_centavos", sa.Integer(), nullable=False, server_default=sa.text("0")
            ),
            sa.Column("observacoes", sa.Text(), nullable=False, server_default=sa.text("''")),
            sa.Column("criado_em", sa.Text(), nullable=False, server_default=AGORA),
            sa.Column("atualizado_em", sa.Text(), nullable=False, server_default=AGORA),
            sa.Column("faturado_em", sa.Text(), nullable=False, server_default=sa.text("''")),
            sa.Column("cancelado_em", sa.Text(), nullable=False, server_default=sa.text("''")),
            sa.Column(
                "motivo_cancelamento", sa.Text(), nullable=False, server_default=sa.text("''")
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.ForeignKeyConstraint(
                ["cliente_id"],
                ["clientes.id"],
                name="fk_pedidos_cliente_id_clientes",
                ondelete="RESTRICT",
            ),
            # A maquina de estados vive em erp/comercial/estados.py; o CHECK e
            # a ultima linha de defesa contra escrita fora dela.
            sa.CheckConstraint(
                "situacao IN ('rascunho', 'aberto', 'aprovado', 'faturado', 'cancelado')",
                name="ck_pedidos_situacao",
            ),
            sa.CheckConstraint("desconto_centavos >= 0", name="ck_pedidos_desconto_nao_negativo"),
            sa.CheckConstraint("frete_centavos >= 0", name="ck_pedidos_frete_nao_negativo"),
            sa.CheckConstraint(
                "total_liquido_centavos >= 0", name="ck_pedidos_total_nao_negativo"
            ),
        )
        op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_pedidos_numero ON pedidos(numero)")
        op.create_index("ix_pedidos_cliente_id", "pedidos", ["cliente_id"])
        op.create_index("ix_pedidos_situacao_emissao", "pedidos", ["situacao", "data_emissao"])
        op.create_index("ix_pedidos_entrega_prevista", "pedidos", ["data_entrega_prevista"])

    if "pedido_itens" not in tabelas:
        op.create_table(
            "pedido_itens",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("pedido_id", sa.Integer(), nullable=False),
            sa.Column("produto_id", sa.Integer(), nullable=False),
            # Copiada no lancamento e editavel: cada poltrona sob encomenda tem
            # tecido, acabamento e medida proprios. Renomear o produto no
            # catalogo nao pode reescrever um pedido ja emitido.
            sa.Column("descricao", sa.Text(), nullable=False),
            sa.Column("quantidade", sa.Integer(), nullable=False, server_default=sa.text("1")),
            sa.Column("preco_unitario_centavos", sa.Integer(), nullable=False),
            sa.Column(
                "desconto_centavos", sa.Integer(), nullable=False, server_default=sa.text("0")
            ),
            sa.Column("total_centavos", sa.Integer(), nullable=False),
            sa.Column("sequencia", sa.Integer(), nullable=False, server_default=sa.text("1")),
            sa.PrimaryKeyConstraint("id"),
            # CASCADE: item nao existe sem o pedido dele.
            sa.ForeignKeyConstraint(
                ["pedido_id"],
                ["pedidos.id"],
                name="fk_pedido_itens_pedido_id_pedidos",
                ondelete="CASCADE",
            ),
            # RESTRICT: produto usado em pedido nao pode sumir do catalogo.
            sa.ForeignKeyConstraint(
                ["produto_id"],
                ["produtos.id"],
                name="fk_pedido_itens_produto_id_produtos",
                ondelete="RESTRICT",
            ),
            sa.CheckConstraint("quantidade > 0", name="ck_pedido_itens_quantidade_positiva"),
            sa.CheckConstraint(
                "preco_unitario_centavos >= 0", name="ck_pedido_itens_preco_nao_negativo"
            ),
            sa.CheckConstraint("total_centavos >= 0", name="ck_pedido_itens_total_nao_negativo"),
        )
        op.create_index("ix_pedido_itens_pedido_id", "pedido_itens", ["pedido_id"])
        op.create_index("ix_pedido_itens_produto_id", "pedido_itens", ["produto_id"])

    # -----------------------------------------------------------------------
    # 3. Entrega passa a saber de qual pedido ela e
    # -----------------------------------------------------------------------
    # Coluna na tabela existente, e nao tabela nova: preserva
    # GET/POST/PUT /api/entregas e as 3 notificacoes que ja leem daqui.
    # Anulavel porque as entregas ja cadastradas nasceram sem pedido.
    if "pedido_id" not in _colunas("entregas_agendadas"):
        op.add_column("entregas_agendadas", sa.Column("pedido_id", sa.Integer(), nullable=True))
        op.create_index("ix_entregas_pedido_id", "entregas_agendadas", ["pedido_id"])

    # -----------------------------------------------------------------------
    # 4. Pagamento passa a saber de qual pedido e de qual parcela ele e
    # -----------------------------------------------------------------------
    colunas_pagamentos = _colunas("pagamentos")
    if "pedido_id" not in colunas_pagamentos:
        op.add_column("pagamentos", sa.Column("pedido_id", sa.Integer(), nullable=True))
        op.create_index("ix_pagamentos_pedido_id", "pagamentos", ["pedido_id"])
    if "parcela" not in colunas_pagamentos:
        op.add_column(
            "pagamentos",
            sa.Column("parcela", sa.Integer(), nullable=False, server_default=sa.text("1")),
        )
    if "total_parcelas" not in colunas_pagamentos:
        op.add_column(
            "pagamentos",
            sa.Column(
                "total_parcelas", sa.Integer(), nullable=False, server_default=sa.text("1")
            ),
        )

    # A FK de entregas/pagamentos para pedidos NAO e criada por ALTER TABLE:
    # o SQLite exige recriar a tabela inteira para isso, o que num banco em
    # producao troca um vinculo declarativo por risco real de perda. A
    # integridade e garantida na camada de aplicacao (erp/comercial), e o
    # indice acima cobre a consulta.


def downgrade() -> None:
    colunas_pagamentos = _colunas("pagamentos")
    if "total_parcelas" in colunas_pagamentos:
        op.drop_column("pagamentos", "total_parcelas")
    if "parcela" in colunas_pagamentos:
        op.drop_column("pagamentos", "parcela")
    if "pedido_id" in colunas_pagamentos:
        op.drop_index("ix_pagamentos_pedido_id", table_name="pagamentos")
        op.drop_column("pagamentos", "pedido_id")

    if "pedido_id" in _colunas("entregas_agendadas"):
        op.drop_index("ix_entregas_pedido_id", table_name="entregas_agendadas")
        op.drop_column("entregas_agendadas", "pedido_id")

    tabelas = _tabelas()
    if "pedido_itens" in tabelas:
        op.drop_table("pedido_itens")
    if "pedidos" in tabelas:
        op.drop_table("pedidos")
    if "produtos" in tabelas:
        op.drop_table("produtos")
