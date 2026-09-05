"""Remove as colunas e a tabela da integracao Asaas

Revision ID: e5c94a17b3d8
Revises: d8f31b06a4e5
Create Date: 2026-09-05 18:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e5c94a17b3d8'
down_revision: Union[str, None] = 'd8f31b06a4e5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Colunas de `pagamentos` que so existiam por causa do gateway.
#
# `tipo_pagamento` NAO esta aqui: "Pix", "Boleto", "Dinheiro" descrevem como o
# dinheiro chegou, e isso continua verdade sem gateway nenhum.
COLUNAS_DO_GATEWAY = (
    'asaas_payment_id',
    'asaas_external_reference',
    'asaas_emissao_estado',
    'asaas_emissao_inicio',
    'pix_payload',
    'pix_qr_code',
    'boleto_url',
    'nosso_numero',
)


def upgrade() -> None:
    """
    Apaga o que a integracao deixou.

    ISTO DESCARTA DADOS, e a decisao de aplica-lo foi tomada sabendo disso: o
    aplicativo ainda nao foi entregue a nenhum cliente, entao nao existe
    cobranca emitida em lugar nenhum. Numa instalacao com historico, esta
    migration perderia o vinculo entre o pagamento local e a cobranca que o
    gerou -- e `downgrade` recria as colunas vazias, nao os valores.

    As colunas saem uma a uma, tolerando ausencia. Um banco que veio do caminho
    de emergencia pode nao ter todas: `garantir_schema_fallback` acompanhou as
    versoes ao longo do tempo, e nem toda instalacao passou por todas.
    """
    conexao = op.get_bind()

    # Os indices primeiro. O SQLite valida os indices existentes ao soltar uma
    # coluna, e recusa com "error in index ... after drop column" se algum
    # ainda a referenciar -- o que acontece aqui, porque `asaas_payment_id`
    # tem indice unico. Derrubar a coluna antes do indice nao e uma ordem
    # possivel.
    indices = list(conexao.exec_driver_sql(
        "SELECT name, sql FROM sqlite_master "
        "WHERE type='index' AND tbl_name='pagamentos' AND sql IS NOT NULL"
    ))
    for nome, sql in indices:
        if any(coluna in (sql or '') for coluna in COLUNAS_DO_GATEWAY):
            op.execute(f'DROP INDEX IF EXISTS "{nome}"')

    existentes = {
        linha[1] for linha in conexao.exec_driver_sql("PRAGMA table_info(pagamentos)")
    }
    for coluna in COLUNAS_DO_GATEWAY:
        if coluna in existentes:
            op.drop_column('pagamentos', coluna)

    # O vinculo entre o cliente local e o cadastro dele no Asaas. Sem o
    # gateway, e uma tabela de ponteiros para lugar nenhum.
    op.execute('DROP TABLE IF EXISTS clientes_asaas')


def downgrade() -> None:
    """
    Recria a forma, e nao o conteudo.

    Quem descer esta revision recupera as colunas vazias e a tabela vazia. E o
    maximo honesto que um downgrade pode oferecer aqui: os valores foram
    descartados no upgrade e nao estao guardados em lugar nenhum.
    """
    for coluna in COLUNAS_DO_GATEWAY:
        op.add_column('pagamentos',
                      sa.Column(coluna, sa.Text(), nullable=True, server_default=''))

    op.create_table(
        'clientes_asaas',
        sa.Column('cliente_id', sa.Integer(), nullable=False),
        sa.Column('asaas_customer_id', sa.Text(), nullable=False, server_default=''),
        sa.Column('asaas_external_reference', sa.Text(), nullable=True, server_default=''),
        sa.Column('asaas_criacao_estado', sa.Text(), nullable=True, server_default=''),
        sa.Column('asaas_criacao_inicio', sa.Text(), nullable=True, server_default=''),
        sa.PrimaryKeyConstraint('cliente_id'),
    )
