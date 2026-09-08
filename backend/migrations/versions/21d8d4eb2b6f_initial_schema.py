"""Initial schema

Revision ID: 21d8d4eb2b6f
Revises: 
Create Date: 2026-08-05 02:18:10.675335

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = '21d8d4eb2b6f'
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('clientes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('nome', sa.Text(), nullable=False),
        sa.Column('cep', sa.Text(), nullable=True),
        sa.Column('rua', sa.Text(), nullable=True),
        sa.Column('bairro', sa.Text(), nullable=True),
        sa.Column('cidade', sa.Text(), nullable=True),
        sa.Column('entrega_retirada', sa.Text(), nullable=False, server_default="'Entrega'"),
        sa.Column('observacoes', sa.Text(), nullable=True, server_default="''"),
        sa.Column('criado_em', sa.Text(), nullable=True),
        sa.Column('atualizado_em', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_table('sessao',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('token', sa.Text(), nullable=False),
        sa.Column('conta', sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_table('historico',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('cliente_id', sa.Integer(), nullable=True),
        sa.Column('cliente_nome', sa.Text(), nullable=True),
        sa.Column('acao', sa.Text(), nullable=False),
        sa.Column('detalhes', sa.Text(), nullable=True, server_default="''"),
        sa.Column('data_hora', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_table('pagamentos',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('cliente_id', sa.Integer(), nullable=False),
        sa.Column('cliente_nome', sa.Text(), nullable=True, server_default="''"),
        # sa.REAL (maiusculo) e o tipo do dialeto; sa.Real nao existe.
        sa.Column('valor', sa.REAL(), nullable=False, server_default="0"),
        sa.Column('descricao', sa.Text(), nullable=True, server_default="''"),
        sa.Column('status', sa.Text(), nullable=False, server_default="'Pendente'"),
        sa.Column('data_pagamento', sa.Text(), nullable=True, server_default="''"),
        sa.Column('data_vencimento', sa.Text(), nullable=True, server_default="''"),
        sa.Column('criado_em', sa.Text(), nullable=True),
        sa.Column('tipo_pagamento', sa.Text(), nullable=False, server_default="'Pix'"),
        sa.Column('asaas_payment_id', sa.Text(), nullable=True, server_default="''"),
        sa.Column('pix_payload', sa.Text(), nullable=True, server_default="''"),
        sa.Column('pix_qr_code', sa.Text(), nullable=True, server_default="''"),
        sa.Column('boleto_url', sa.Text(), nullable=True, server_default="''"),
        sa.Column('nosso_numero', sa.Text(), nullable=True, server_default="''"),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_table('clientes_asaas',
        sa.Column('cliente_id', sa.Integer(), nullable=False),
        sa.Column('asaas_customer_id', sa.Text(), nullable=False, server_default="''"),
        sa.PrimaryKeyConstraint('cliente_id')
    )

    op.create_table('entregas_agendadas',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('cliente_id', sa.Integer(), nullable=False),
        sa.Column('cliente_nome', sa.Text(), nullable=True, server_default="''"),
        sa.Column('data_entrega', sa.Text(), nullable=False),
        sa.Column('hora_entrega', sa.Text(), nullable=True, server_default="''"),
        sa.Column('descricao', sa.Text(), nullable=True, server_default="''"),
        sa.Column('status', sa.Text(), nullable=False, server_default="'Pendente'"),
        sa.Column('criado_em', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    op.drop_table('entregas_agendadas')
    op.drop_table('clientes_asaas')
    op.drop_table('pagamentos')
    op.drop_table('historico')
    op.drop_table('sessao')
    op.drop_table('clientes')
