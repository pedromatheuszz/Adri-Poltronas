"""
Acesso a dados do catalogo e dos pedidos.

Aqui mora SQL, e so SQL. As regras de negocio -- o que pode virar o que, como
os totais sao calculados, quando o faturamento pode acontecer -- ficam em
`servico.py`. A separacao existe porque `database.py` cresceu para 860 linhas
misturando as duas coisas, e nao ha como testar uma regra sem subir um banco.

Todas as funcoes recebem a conexao de fora: quem chama controla a transacao,
e e isso que permite faturar um pedido (gravar situacao + emitir N parcelas)
sem deixar metade do trabalho feito se algo falhar no meio.
"""
from __future__ import annotations

import sqlite3
from typing import Any, Iterable, Optional


def _dict(linha: Optional[sqlite3.Row]) -> Optional[dict]:
    return dict(linha) if linha is not None else None


def _dicts(linhas: Iterable[sqlite3.Row]) -> list[dict]:
    return [dict(linha) for linha in linhas]


# =============================================================================
# Produtos
# =============================================================================
def listar_produtos(conexao, busca: str = "", incluir_inativos: bool = False) -> list[dict]:
    sql = "SELECT * FROM produtos WHERE 1=1"
    parametros: list[Any] = []
    if not incluir_inativos:
        sql += " AND ativo = 1"
    termo = (busca or "").strip()
    if termo:
        sql += " AND (codigo LIKE ? OR descricao LIKE ?)"
        parametros += [f"%{termo}%", f"%{termo}%"]
    sql += " ORDER BY descricao COLLATE NOCASE"
    return _dicts(conexao.execute(sql, parametros))


def obter_produto(conexao, produto_id: int) -> Optional[dict]:
    return _dict(conexao.execute("SELECT * FROM produtos WHERE id = ?", (produto_id,)).fetchone())


def codigo_em_uso(conexao, codigo: str, ignorar_id: Optional[int] = None) -> bool:
    sql = "SELECT 1 FROM produtos WHERE codigo = ? AND ativo = 1"
    parametros: list[Any] = [codigo]
    if ignorar_id:
        sql += " AND id != ?"
        parametros.append(ignorar_id)
    return conexao.execute(sql, parametros).fetchone() is not None


def inserir_produto(conexao, dados: dict) -> int:
    conexao.execute(
        """INSERT INTO produtos (codigo, descricao, unidade, preco_venda_centavos, observacoes)
           VALUES (?, ?, ?, ?, ?)""",
        (
            dados["codigo"],
            dados["descricao"],
            dados["unidade"],
            dados["preco_venda_centavos"],
            dados.get("observacoes", ""),
        ),
    )
    return conexao.execute("SELECT last_insert_rowid()").fetchone()[0]


def atualizar_produto(conexao, produto_id: int, dados: dict) -> None:
    conexao.execute(
        """UPDATE produtos
              SET codigo = ?, descricao = ?, unidade = ?, preco_venda_centavos = ?,
                  observacoes = ?, atualizado_em = datetime('now', 'localtime')
            WHERE id = ?""",
        (
            dados["codigo"],
            dados["descricao"],
            dados["unidade"],
            dados["preco_venda_centavos"],
            dados.get("observacoes", ""),
            produto_id,
        ),
    )


def inativar_produto(conexao, produto_id: int) -> None:
    """
    Inativa em vez de apagar.

    Produto usado em pedido nao pode sumir: o pedido antigo perderia a
    referencia, e a FK e RESTRICT justamente para impedir isso.
    """
    conexao.execute(
        "UPDATE produtos SET ativo = 0, atualizado_em = datetime('now', 'localtime') WHERE id = ?",
        (produto_id,),
    )


def produto_usado_em_pedido(conexao, produto_id: int) -> bool:
    return conexao.execute(
        "SELECT 1 FROM pedido_itens WHERE produto_id = ? LIMIT 1", (produto_id,)
    ).fetchone() is not None


# =============================================================================
# Pedidos
# =============================================================================
def proximo_numero(conexao, exercicio: str) -> str:
    """
    Sequencia por ano: PED-2026-000001.

    Deriva do maior numero ja gravado no exercicio em vez de contar linhas --
    contar quebraria se um pedido fosse removido, e reemitiria um numero que
    ja circulou impresso.
    """
    prefixo = f"PED-{exercicio}-"
    ultimo = conexao.execute(
        "SELECT numero FROM pedidos WHERE numero LIKE ? ORDER BY numero DESC LIMIT 1",
        (f"{prefixo}%",),
    ).fetchone()
    sequencial = int(ultimo[0].rsplit("-", 1)[1]) + 1 if ultimo else 1
    return f"{prefixo}{sequencial:06d}"


def listar_pedidos(conexao, situacao: str = "", busca: str = "") -> list[dict]:
    sql = """SELECT p.*,
                    (SELECT COUNT(*) FROM pedido_itens i WHERE i.pedido_id = p.id) AS qtd_itens
               FROM pedidos p
              WHERE 1=1"""
    parametros: list[Any] = []
    if situacao:
        sql += " AND p.situacao = ?"
        parametros.append(situacao)
    termo = (busca or "").strip()
    if termo:
        sql += " AND (p.cliente_nome LIKE ? OR p.numero LIKE ?)"
        parametros += [f"%{termo}%", f"%{termo}%"]
    sql += " ORDER BY p.id DESC"
    return _dicts(conexao.execute(sql, parametros))


def obter_pedido(conexao, pedido_id: int) -> Optional[dict]:
    return _dict(conexao.execute("SELECT * FROM pedidos WHERE id = ?", (pedido_id,)).fetchone())


def obter_pedido_com_itens(conexao, pedido_id: int) -> Optional[dict]:
    pedido = obter_pedido(conexao, pedido_id)
    if pedido is None:
        return None
    pedido["itens"] = listar_itens(conexao, pedido_id)
    return pedido


def inserir_pedido(conexao, dados: dict) -> int:
    conexao.execute(
        """INSERT INTO pedidos (numero, cliente_id, cliente_nome, data_emissao,
                                data_entrega_prevista, desconto_centavos, frete_centavos,
                                observacoes)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            dados["numero"],
            dados["cliente_id"],
            dados["cliente_nome"],
            dados["data_emissao"],
            dados.get("data_entrega_prevista", ""),
            dados.get("desconto_centavos", 0),
            dados.get("frete_centavos", 0),
            dados.get("observacoes", ""),
        ),
    )
    return conexao.execute("SELECT last_insert_rowid()").fetchone()[0]


def atualizar_cabecalho(conexao, pedido_id: int, dados: dict) -> None:
    conexao.execute(
        """UPDATE pedidos
              SET cliente_id = ?, cliente_nome = ?, data_entrega_prevista = ?,
                  desconto_centavos = ?, frete_centavos = ?, observacoes = ?,
                  atualizado_em = datetime('now', 'localtime')
            WHERE id = ?""",
        (
            dados["cliente_id"],
            dados["cliente_nome"],
            dados.get("data_entrega_prevista", ""),
            dados.get("desconto_centavos", 0),
            dados.get("frete_centavos", 0),
            dados.get("observacoes", ""),
            pedido_id,
        ),
    )


def atualizar_totais(conexao, pedido_id: int, bruto: int, liquido: int) -> None:
    conexao.execute(
        """UPDATE pedidos
              SET total_bruto_centavos = ?, total_liquido_centavos = ?,
                  atualizado_em = datetime('now', 'localtime')
            WHERE id = ?""",
        (bruto, liquido, pedido_id),
    )


def mudar_situacao(conexao, pedido_id: int, situacao: str, extras: Optional[dict] = None) -> None:
    campos = ["situacao = ?", "atualizado_em = datetime('now', 'localtime')"]
    parametros: list[Any] = [situacao]
    for coluna, valor in (extras or {}).items():
        campos.append(f"{coluna} = ?")
        parametros.append(valor)
    parametros.append(pedido_id)
    conexao.execute(f"UPDATE pedidos SET {', '.join(campos)} WHERE id = ?", parametros)


# --- Itens -------------------------------------------------------------------
def listar_itens(conexao, pedido_id: int) -> list[dict]:
    return _dicts(
        conexao.execute(
            """SELECT i.*, pr.codigo AS produto_codigo, pr.unidade AS produto_unidade
                 FROM pedido_itens i
                 JOIN produtos pr ON pr.id = i.produto_id
                WHERE i.pedido_id = ?
                ORDER BY i.sequencia, i.id""",
            (pedido_id,),
        )
    )


def inserir_item(conexao, pedido_id: int, dados: dict) -> int:
    proxima = conexao.execute(
        "SELECT COALESCE(MAX(sequencia), 0) + 1 FROM pedido_itens WHERE pedido_id = ?",
        (pedido_id,),
    ).fetchone()[0]
    conexao.execute(
        """INSERT INTO pedido_itens (pedido_id, produto_id, descricao, quantidade,
                                     preco_unitario_centavos, desconto_centavos,
                                     total_centavos, sequencia)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            pedido_id,
            dados["produto_id"],
            dados["descricao"],
            dados["quantidade"],
            dados["preco_unitario_centavos"],
            dados.get("desconto_centavos", 0),
            dados["total_centavos"],
            proxima,
        ),
    )
    return conexao.execute("SELECT last_insert_rowid()").fetchone()[0]


def remover_item(conexao, pedido_id: int, item_id: int) -> int:
    cursor = conexao.execute(
        "DELETE FROM pedido_itens WHERE id = ? AND pedido_id = ?", (item_id, pedido_id)
    )
    return cursor.rowcount


def somar_itens(conexao, pedido_id: int) -> int:
    total = conexao.execute(
        "SELECT COALESCE(SUM(total_centavos), 0) FROM pedido_itens WHERE pedido_id = ?",
        (pedido_id,),
    ).fetchone()[0]
    return int(total)


# --- Vinculos ----------------------------------------------------------------
def parcelas_do_pedido(conexao, pedido_id: int) -> list[dict]:
    return _dicts(
        conexao.execute(
            "SELECT * FROM pagamentos WHERE pedido_id = ? ORDER BY parcela", (pedido_id,)
        )
    )


def entregas_do_pedido(conexao, pedido_id: int) -> list[dict]:
    return _dicts(
        conexao.execute(
            "SELECT * FROM entregas_agendadas WHERE pedido_id = ? ORDER BY data_entrega",
            (pedido_id,),
        )
    )


def inserir_parcela(conexao, dados: dict) -> int:
    """
    Uma parcela a receber e uma linha em `pagamentos`.

    Reusar a tabela existente, em vez de criar `titulos`, mantem em pe toda a
    maquina de cobranca que ja funciona: Pix, boleto, webhook do Asaas e a
    tela de Pagamentos.

    O valor chega em CENTAVOS e e gravado em centavos. Ate a versao 1.1 ele
    passava por `round(centavos / 100, 2)` aqui, e o rateio exato feito pelo
    `dinheiro.ratear` se perdia na conversao: tres parcelas de um pedido de
    R$ 100,00 viravam 33.33 / 33.33 / 33.34 em ponto flutuante binario, cuja
    soma nao e 100,00.

    `valor` (REAL) continua sendo gravado a partir dos centavos, para que
    consultas e relatorios que dependem dele sigam funcionando enquanto as
    duas colunas convivem.
    """
    centavos = int(dados["valor_centavos"])
    conexao.execute(
        """INSERT INTO pagamentos (cliente_id, cliente_nome, valor, valor_centavos,
                                   descricao, status, data_vencimento,
                                   tipo_pagamento, pedido_id, parcela, total_parcelas)
           VALUES (?, ?, ?, ?, ?, 'Pendente', ?, ?, ?, ?, ?)""",
        (
            dados["cliente_id"],
            dados["cliente_nome"],
            round(centavos / 100, 2),
            centavos,
            dados["descricao"],
            dados["data_vencimento"],
            dados.get("tipo_pagamento", "Pix"),
            dados["pedido_id"],
            dados["parcela"],
            dados["total_parcelas"],
        ),
    )
    return conexao.execute("SELECT last_insert_rowid()").fetchone()[0]
