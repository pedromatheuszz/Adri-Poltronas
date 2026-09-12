"""Corrige colunas cujo DEFAULT virou a string "''" em vez de vazio

BUG DE ORIGEM
A migration inicial declara `server_default="''"`. Para o SQLAlchemy, uma str
em `server_default` e uma EXPRESSAO SQL literal -- e ela ja vem aspeada. O DDL
gerado ficou `DEFAULT ''''''`, que o SQLite guarda como a string de DOIS
caracteres `''`, e nao como texto vazio.

POR QUE ISSO IMPORTA
Bancos criados pelas migrations (ou seja, toda instalacao NOVA) recebiam `''`
onde deveria haver vazio. Duas consequencias reais:

1. `ux_pagamentos_asaas_payment_id` e um indice unico parcial que ignora o
   vazio. Como `''` nao e vazio, o indice passou a valer para todo lancamento
   sem cobranca Asaas -- e o SEGUNDO recebimento cadastrado numa instalacao
   nova falhava com "UNIQUE constraint failed", devolvendo HTTP 500.
2. O front decide entre "Gerar Cobranca" e "Confirmar" com
   `if (!p.asaas_payment_id)`. Em JavaScript a string `"''"` e *truthy*, entao
   a tela oferecia "Confirmar" para uma cobranca que nunca foi emitida.

O banco em producao NAO tem o problema: o schema dele veio do caminho legado
(`criar_tabela()`, com `DEFAULT ''` cru) e foi reconciliado por f4c8b2d6e1a0.
Por isso a correcao e condicional -- onde ja esta certo, nao toca em nada.

Revision ID: d1e7b3f5620a
Revises: c9f4e2a71b83
Create Date: 2026-09-01 15:10:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d1e7b3f5620a"
down_revision: str | None = "c9f4e2a71b83"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# O valor errado: dois apostrofos literais.
VALOR_ERRADO = "''"

# Colunas de texto que nasceram com o default defeituoso.
COLUNAS_AFETADAS = {
    "clientes": ("observacoes", "excluido_em"),
    "pagamentos": (
        "cliente_nome", "descricao", "data_pagamento", "data_vencimento",
        "asaas_payment_id", "pix_payload", "pix_qr_code", "boleto_url",
        "nosso_numero", "asaas_external_reference", "asaas_emissao_estado",
        "asaas_emissao_inicio",
    ),
    "entregas_agendadas": ("cliente_nome", "hora_entrega", "descricao"),
    "historico": ("detalhes",),
    "clientes_asaas": (
        "asaas_customer_id", "asaas_external_reference",
        "asaas_criacao_estado", "asaas_criacao_inicio",
    ),
}


def _colunas_existentes(tabela: str) -> set:
    inspetor = sa.inspect(op.get_bind())
    if tabela not in inspetor.get_table_names():
        return set()
    return {coluna["name"] for coluna in inspetor.get_columns(tabela)}


def upgrade() -> None:
    conexao = op.get_bind()

    # -----------------------------------------------------------------------
    # 1. Normaliza os dados ja gravados
    # -----------------------------------------------------------------------
    # Roda sempre: mesmo num banco com o default correto, uma linha pode ter
    # recebido o valor errado antes desta correcao.
    total = 0
    for tabela, colunas in COLUNAS_AFETADAS.items():
        presentes = _colunas_existentes(tabela)
        for coluna in colunas:
            if coluna not in presentes:
                continue
            resultado = conexao.execute(
                sa.text(f"UPDATE {tabela} SET {coluna} = '' WHERE {coluna} = :errado"),  # noqa: S608 - fragmento constante do proprio codigo, nunca entrada do usuario
                {"errado": VALOR_ERRADO},
            )
            total += resultado.rowcount or 0
    if total:
        print(f"[migration] {total} valor(es) '' normalizado(s) para texto vazio.")

    # -----------------------------------------------------------------------
    # 2. Corrige o DEFAULT das colunas
    # -----------------------------------------------------------------------
    # O SQLite nao tem ALTER COLUMN: mudar um default exige recriar a tabela.
    # `batch_alter_table` faz isso (tabela temporaria -> copia -> troca), e por
    # isso a correcao so acontece onde o defeito EXISTE. Num banco ja correto
    # -- o caso de producao -- nada e recriado, e o risco fica em zero.
    #
    # Quando o defeito existe, o banco foi criado pelas migrations e esta na
    # primeira abertura: recriar a tabela ali e barato e sem carga de dados.
    for tabela, colunas in COLUNAS_AFETADAS.items():
        if tabela not in sa.inspect(conexao).get_table_names():
            continue
        defeituosas = [
            coluna["name"]
            for coluna in sa.inspect(conexao).get_columns(tabela)
            if coluna["name"] in colunas
            and (coluna.get("default") or "").replace("'", "") == ""
            and (coluna.get("default") or "").count("'") > 2
        ]
        if not defeituosas:
            continue
        print(f"[migration] corrigindo DEFAULT em {tabela}: {', '.join(defeituosas)}")
        with op.batch_alter_table(tabela, recreate="always") as lote:
            for coluna in defeituosas:
                lote.alter_column(
                    coluna, existing_type=sa.Text(), server_default=sa.text("''")
                )


def downgrade() -> None:
    # Sem volta: o estado anterior e um defeito. Reintroduzi-lo devolveria o
    # HTTP 500 no segundo recebimento de toda instalacao nova.
    pass
