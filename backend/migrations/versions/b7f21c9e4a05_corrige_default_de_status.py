"""Corrige os DEFAULT de status/tipo que viraram texto COM aspas

BUG DE ORIGEM
E o mesmo defeito que `d1e7b3f5620a` corrigiu para as colunas de texto vazio,
em tres colunas que ficaram de fora dela.

Para o SQLAlchemy, uma `str` em `server_default` e um VALOR a ser aspeado, nao
SQL cru -- quem quer SQL cru usa `sa.text(...)`. A migration inicial declarou
`server_default="'Pendente'"` achando que as aspas internas eram necessarias.
Elas foram aspeadas de novo: o DDL saiu `DEFAULT '''Pendente'''`, e o SQLite
guarda a string de DEZ caracteres `'Pendente'` -- com apostrofos dentro --
em vez de `Pendente`.

Colunas afetadas, todas em banco criado pelas migrations:

    entregas_agendadas.status      DEFAULT '''Pendente'''
    pagamentos.status              DEFAULT '''Pendente'''
    pagamentos.tipo_pagamento      DEFAULT '''Pix'''

POR QUE ISSO IMPORTA
Todo filtro por esses valores erra em silencio -- nao levanta erro, so nao
casa. Tres consequencias reais, uma delas introduzida na 1.5.1:

1. `cancelar_entregas_do_pedido()` roda `WHERE status IN ('Pendente',
   'Em andamento')`. Numa instalacao nova, nenhuma entrega criada pelo DEFAULT
   casa, e cancelar um pedido nao cancela entrega nenhuma. A correcao do
   achado BUG-06 da auditoria ficava inerte exatamente onde precisava valer.
2. `_vinculos_que_impedem_exclusao()` conta parcelas `status IN ('Pendente',
   'Atrasado')`. Uma parcela gravada pelo DEFAULT nao e contada, e o cliente
   fica excluivel apesar de dever -- o oposto do que o achado BUG-04 pediu.
3. As notificacoes de entrega excluem os status encerrados por
   `status NOT IN (...)`. Com o valor aspeado a comparacao tambem nao casa.

Por que os testes nao pegaram: a suite monta o banco por `criar_tabela()` ->
`schema_fallback`, que escreve `DEFAULT 'Pendente'` cru e portanto correto. O
caminho das migrations -- que e o de TODA instalacao nova -- nao era exercitado
por nenhum teste funcional. O teste que fecha essa lacuna acompanha esta
migration em `tests/test_migrations_schema.py`.

O banco de producao NAO tem o problema: veio do caminho legado e foi
reconciliado por `f4c8b2d6e1a0`. Por isso a correcao e condicional -- onde ja
esta certo, nada e recriado.

Revision ID: b7f21c9e4a05
Revises: e5c94a17b3d8
Create Date: 2026-09-07 15:20:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b7f21c9e4a05"
down_revision: str | None = "e5c94a17b3d8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# tabela -> coluna -> valor correto (sem os apostrofos parasitas).
COLUNAS_AFETADAS = {
    "entregas_agendadas": {"status": "Pendente"},
    "pagamentos": {"status": "Pendente", "tipo_pagamento": "Pix"},
}

# O mesmo defeito numa coluna NUMERICA: `pagamentos.valor` (REAL) saiu com
# `DEFAULT '0'`, texto.
#
# Aqui ninguem se machuca, e vale dizer por que: a afinidade REAL do SQLite
# converte o texto '0' para 0.0 na gravacao -- conferido, `typeof(valor)`
# devolve 'real' e SUM() funciona. Nas colunas TEXT acima nao ha afinidade que
# resgate, e por isso la o estrago era real.
#
# Corrigido junto assim mesmo: um DDL que diz `DEFAULT '0'` numa coluna REAL
# engana quem le o schema, e a tabela ja e recriada por causa das outras duas.
COLUNAS_NUMERICAS = {
    "pagamentos": {"valor": "0"},
}


def _colunas(conexao, tabela: str) -> dict:
    inspetor = sa.inspect(conexao)
    if tabela not in inspetor.get_table_names():
        return {}
    return {coluna["name"]: coluna for coluna in inspetor.get_columns(tabela)}


def upgrade() -> None:
    conexao = op.get_bind()

    # -----------------------------------------------------------------------
    # 1. Normaliza os dados ja gravados
    # -----------------------------------------------------------------------
    # Roda sempre, inclusive num banco cujo DEFAULT ja esteja certo: uma linha
    # pode ter recebido o valor aspeado antes desta correcao. E o passo que
    # realmente destrava a operacao -- uma entrega com status `'Pendente'`
    # nunca sairia da agenda por caminho nenhum da interface.
    total = 0
    for tabela, colunas in COLUNAS_AFETADAS.items():
        presentes = _colunas(conexao, tabela)
        for coluna, correto in colunas.items():
            if coluna not in presentes:
                continue
            resultado = conexao.execute(
                sa.text(f"UPDATE {tabela} SET {coluna} = :correto WHERE {coluna} = :errado"),  # noqa: S608 - nomes vem de COLUNAS_AFETADAS, constante do proprio codigo
                {"correto": correto, "errado": f"'{correto}'"},
            )
            total += resultado.rowcount or 0
    if total:
        print(f"[migration] {total} valor(es) de status/tipo desaspeado(s).")

    # -----------------------------------------------------------------------
    # 2. Corrige o DEFAULT
    # -----------------------------------------------------------------------
    # O SQLite nao tem ALTER COLUMN: mudar um default exige recriar a tabela.
    # `batch_alter_table` faz isso, e por isso so entra onde o defeito EXISTE.
    # Num banco correto -- producao -- nada e recriado e o risco fica em zero.
    for tabela, colunas in COLUNAS_AFETADAS.items():
        presentes = _colunas(conexao, tabela)
        defeituosas = {}
        for coluna, correto in colunas.items():
            if coluna not in presentes:
                continue
            atual = presentes[coluna].get("default") or ""
            # O default correto e "'Pendente'" (3 apostrofos ao todo, um par
            # externo). O defeituoso e "'''Pendente'''" -- seis. Comparar o
            # texto desaspeado evita depender da contagem exata.
            if atual.strip("'") == f"'{correto}'".strip("'") and atual.count("'") > 2:
                defeituosas[coluna] = correto
        # As numericas da mesma tabela entram na MESMA recriacao: recriar
        # `pagamentos` duas vezes seria o dobro do risco pelo mesmo resultado.
        numericas = {}
        for coluna, correto in COLUNAS_NUMERICAS.get(tabela, {}).items():
            if coluna not in presentes:
                continue
            atual = presentes[coluna].get("default") or ""
            if atual.strip("'") == correto and "'" in atual:
                numericas[coluna] = correto

        if not defeituosas and not numericas:
            continue
        alteradas = list(defeituosas) + list(numericas)
        print(f"[migration] corrigindo DEFAULT em {tabela}: {', '.join(alteradas)}")
        with op.batch_alter_table(tabela, recreate="always") as lote:
            for coluna, correto in defeituosas.items():
                lote.alter_column(
                    coluna,
                    existing_type=sa.Text(),
                    existing_nullable=False,
                    # `sa.text` = SQL cru. E a forma que a migration inicial
                    # deveria ter usado, e a razao de este arquivo existir.
                    server_default=sa.text(f"'{correto}'"),
                )
            for coluna, correto in numericas.items():
                lote.alter_column(
                    coluna,
                    existing_type=sa.Float(),
                    server_default=sa.text(correto),
                )


def downgrade() -> None:
    # Sem volta: o estado anterior e um defeito que deixa entrega cancelada
    # viva na agenda e parcela pendente invisivel para a trava de exclusao.
    pass
