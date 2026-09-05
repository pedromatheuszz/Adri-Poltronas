"""Estado da licenca de uso do aplicativo

Revision ID: d8f31b06a4e5
Revises: c4d81a5f9e37
Create Date: 2026-09-05 02:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd8f31b06a4e5'
down_revision: Union[str, None] = 'c4d81a5f9e37'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Uma copia do estado da licenca. A outra vive num arquivo cifrado no
    # perfil do usuario -- ver o cabecalho de `backend/licenca.py` para por que
    # sao duas.
    #
    # Em resumo: so no banco, restaurar um backup antigo devolveria o prazo de
    # teste, e restaurar backup e funcao legitima e documentada deste app. So
    # no arquivo, apagar o arquivo reiniciaria a contagem. Nos dois, a
    # reconciliacao pega sempre o lado mais restritivo.
    #
    # Linha unica: `licenca` descreve ESTA instalacao, nao um historico.
    op.create_table(
        'licenca',
        # Primeira abertura observada. A contagem dos 30 dias sai daqui.
        sa.Column('instalado_em', sa.Text(), nullable=False, server_default=''),
        # Marca d'agua do relogio: a data mais adiantada ja vista, que nunca
        # retrocede. Atrasar o relogio do sistema congela a contagem em vez de
        # reverte-la.
        sa.Column('visto_em', sa.Text(), nullable=False, server_default=''),
        # 'teste' | 'paga'. 'expirada' e derivado da data, e nao gravado: a
        # expiracao e uma consequencia do calendario, e grava-la criaria um
        # segundo lugar onde ela poderia estar errada.
        sa.Column('estado', sa.Text(), nullable=False, server_default='teste'),
        # Id da cobranca no Mercado Pago -- da que foi paga, ou da que esta
        # aberta esperando pagamento.
        sa.Column('pagamento_id', sa.Text(), nullable=False, server_default=''),
        sa.Column('pago_em', sa.Text(), nullable=False, server_default=''),
        # `external_reference` da cobranca: liga o pagamento a esta instalacao.
        sa.Column('referencia', sa.Text(), nullable=False, server_default=''),
    )


def downgrade() -> None:
    op.drop_table('licenca')
