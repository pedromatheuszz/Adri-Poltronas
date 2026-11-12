"""
Estoque: o razao de quantidade e a disponibilidade derivada dos pedidos.

Duas verdades que este modulo junta, cada uma no lugar certo:

* QUANTO EXISTE vem do livro-razao `estoque_movimentos`. Nao ha coluna de
  quantidade em `produtos`: o total e sempre a soma dos lancamentos, e
  corrigir um erro de contagem e lancar o ajuste -- nao reescrever o
  presente. O razao nunca e editado nem apagado pelo mesmo motivo que a
  auditoria nao e: sem o historico, ninguem consegue explicar por que o
  total e o que e.

* QUANTO ESTA LIVRE vem dos proprios pedidos. Itens de pedidos aprovados e
  faturados com janela de aluguel sao poltronas prometidas naquele periodo
  -- a reserva e DERIVADA, nao gravada. Rascunho nao reserva (e um papel),
  aberto nao reserva (e uma proposta), mas aparece como "em negociacao"
  para o operador enxergar a disputa antes de ela virar problema.

O item sem datas de aluguel e tratado como OCUPANDO QUALQUER PERIODO
consultado. E conservador de proposito: uma locacao sem janela e a unica
situacao em que o sistema nao sabe devolver, e prometer a mesma poltrona
duas vezes e exatamente o erro que o controle existe para impedir. O
pedido tem datas de aluguel no cabecalho no formato DD/MM (recorrente), que
nao resolve para uma janela absoluta -- por isso a janela vem do ITEM, que
grava AAAA-MM-DD.

Total zero significa "estoque nao configurado" para aquele produto: o
catalogo continua sendo catalogo, e nenhuma reserva e conferida. Isso
preserva o comportamento das instalacoes que so usam Produtos como
catalogo -- o README sempre disse que os dois conceitos sao diferentes.
"""
from __future__ import annotations

import datetime
import sqlite3

# Situacoes de pedido que consomem a disponibilidade: a partir da aprovacao
# existe compromisso com o cliente. Faturado continua contando ate o fim da
# janela de aluguel -- a poltrona devolvida e quem devolve, via baixa no razao
# ou fim do periodo.
SITUACOES_QUE_RESERVAM = ("aprovado", "faturado")

# Aberto ainda e proposta: nao reserva, mas disputa o mesmo equipamento e o
# operador precisa ver isso ANTES de aprovar os dois.
SITUACOES_EM_NEGOCIACAO = ("aberto",)

TIPOS_DE_MOVIMENTO = ("aquisicao", "baixa", "ajuste")

# Data impossivel no futuro, usada como "sem fim" nas comparacoes de janela.
_SEM_FIM = "9999-12-31"


class EstoqueInvalido(Exception):
    """Lancamento de movimento que o razao nao aceita."""


def _hoje() -> str:
    return datetime.date.today().isoformat()


def total_do_produto(conexao: sqlite3.Connection, produto_id: int) -> int:
    """Quantas unidades existem, pela soma do razao."""
    linha = conexao.execute(
        "SELECT COALESCE(SUM(delta), 0) FROM estoque_movimentos WHERE produto_id = ?",
        (produto_id,),
    ).fetchone()
    return int(linha[0])


def _intervalo(item: dict) -> tuple[int | None, int | None]:
    """Converte datas inclusivas em ordinais para a varredura de reservas."""
    inicio = (item.get("data_inicio_aluguel") or "").strip()
    fim = (item.get("data_fim_aluguel") or "").strip()
    if bool(inicio) != bool(fim):
        raise EstoqueInvalido("O item tem uma janela de aluguel incompleta; revise as datas.")
    if not inicio:
        return None, None
    try:
        inicio_num = datetime.date.fromisoformat(inicio).toordinal()
        fim_num = datetime.date.fromisoformat(fim).toordinal()
    except ValueError as erro:
        raise EstoqueInvalido("O item contém uma data de aluguel inválida; revise o pedido.") from erro
    if fim_num < inicio_num:
        raise EstoqueInvalido("O término do aluguel antecede o início; revise o pedido.")
    return inicio_num, fim_num


def _pico_de_reservas(intervalos: list[tuple[int, int | None, int | None]]) -> int:
    """Maior quantidade simultânea; datas finais são consideradas inclusivas."""
    corrente = 0
    eventos: dict[int, int] = {}
    for quantidade, inicio, fim in intervalos:
        if quantidade <= 0:
            raise EstoqueInvalido("A reserva contém uma quantidade inválida.")
        if inicio is None:
            corrente += quantidade
        else:
            eventos[inicio] = eventos.get(inicio, 0) + quantidade
        if fim is not None:
            dia_seguinte = fim + 1
            eventos[dia_seguinte] = eventos.get(dia_seguinte, 0) - quantidade

    pico = corrente
    for dia in sorted(eventos):
        corrente += eventos[dia]
        pico = max(pico, corrente)
    return pico


def _reservas_confirmadas(
    conexao: sqlite3.Connection, excluir_pedido_id: int | None = None,
) -> list[dict]:
    """Itens de pedidos que já comprometem estoque, inclusive legados sem data."""
    parametros: list[object] = list(SITUACOES_QUE_RESERVAM)
    exclusao = ""
    if excluir_pedido_id is not None:
        exclusao = " AND p.id != ?"
        parametros.append(excluir_pedido_id)
    return [dict(linha) for linha in conexao.execute(
        """SELECT i.produto_id, i.quantidade, i.data_inicio_aluguel,
                  i.data_fim_aluguel, pr.codigo AS produto_codigo
             FROM pedido_itens i
             JOIN pedidos p ON p.id = i.pedido_id
             JOIN produtos pr ON pr.id = i.produto_id
            WHERE p.situacao IN (?, ?)""" + exclusao,  # noqa: S608
        parametros,
    ).fetchall()]


def validar_aprovacao_pedido(conexao: sqlite3.Connection, pedido_id: int) -> None:
    """Recusa aprovação que ultrapasse o estoque em qualquer dia da locação."""
    itens_pedido = [dict(linha) for linha in conexao.execute(
        """SELECT i.produto_id, i.quantidade, i.data_inicio_aluguel,
                  i.data_fim_aluguel, pr.codigo AS produto_codigo
             FROM pedido_itens i JOIN produtos pr ON pr.id = i.produto_id
            WHERE i.pedido_id = ?""",
        (pedido_id,),
    ).fetchall()]
    if not itens_pedido:
        raise EstoqueInvalido("Um pedido sem itens não pode ser aprovado.")

    existentes = _reservas_confirmadas(conexao, excluir_pedido_id=pedido_id)
    por_produto: dict[int, list[tuple[int, int | None, int | None]]] = {}
    codigos: dict[int, str] = {}
    for item in existentes + itens_pedido:
        produto_id = int(item["produto_id"])
        inicio, fim = _intervalo(item)
        por_produto.setdefault(produto_id, []).append((int(item["quantidade"]), inicio, fim))
        codigos[produto_id] = item.get("produto_codigo") or str(produto_id)

    for produto_id, intervalos in por_produto.items():
        total = total_do_produto(conexao, produto_id)
        # Produtos sem razão de estoque continuam funcionando como catálogo.
        if total == 0:
            continue
        if total < 0:
            raise EstoqueInvalido(
                f"Produto {codigos[produto_id]} tem saldo de estoque negativo ({total})."
            )
        pico = _pico_de_reservas(intervalos)
        if pico > total:
            raise EstoqueInvalido(
                f"Produto {codigos[produto_id]}: há {total} unidade(s) no estoque, "
                f"mas a aprovação deixaria {pico} unidade(s) reservadas ao mesmo tempo."
            )


def _pico_reservado_produto(conexao: sqlite3.Connection, produto_id: int) -> int:
    itens = [item for item in _reservas_confirmadas(conexao) if int(item["produto_id"]) == produto_id]
    intervalos = []
    for item in itens:
        inicio, fim = _intervalo(item)
        intervalos.append((int(item["quantidade"]), inicio, fim))
    return _pico_de_reservas(intervalos) if intervalos else 0


def _janela_sql() -> str:
    """
    Fragmento SQL que responde se o item ocupa o periodo consultado.

    Item sem nenhuma data ocupa sempre (ver o cabecalho do modulo). Item com
    inicio ocupa de `inicio` em diante, com ou sem fim. As datas sao
    AAAA-MM-DD, em que a comparacao de texto e a comparacao de data.
    """
    return (
        "(i.data_inicio_aluguel = '' AND i.data_fim_aluguel = '') "
        "OR (i.data_inicio_aluguel <= ? AND (i.data_fim_aluguel = '' "
        "OR i.data_fim_aluguel >= ?))"
    )


def quantidade_reservada(
    conexao: sqlite3.Connection, produto_id: int, inicio: str, fim: str,
    situacoes: tuple[str, ...],
) -> tuple[int, int]:
    """
    (reservado, sem_janela) que o produto tem no periodo, para as situacoes.

    `sem_janela` vem separado porque e a parte da reserva que ninguem consegue
    agendar por data -- o operador precisa saber que ela existe, nao apenas
    somar os numeros e achar que tudo tem devolucao marcada.
    """
    if not situacoes:
        return 0, 0

    marcadores = ", ".join("?" * len(situacoes))
    janela = _janela_sql()
    sql = (
        f"SELECT COALESCE(SUM(i.quantidade), 0), COALESCE(SUM(CASE "  # noqa: S608 - marcadores e janela vem do proprio codigo
        f"WHEN i.data_inicio_aluguel = '' AND i.data_fim_aluguel = '' "
        f"THEN i.quantidade ELSE 0 END), 0) "
        f"FROM pedido_itens i JOIN pedidos p ON p.id = i.pedido_id "
        f"WHERE i.produto_id = ? AND p.situacao IN ({marcadores}) "
        f"AND ({janela})"
    )
    linha = conexao.execute(
        sql, (produto_id, *situacoes, fim, inicio)).fetchone()
    return int(linha[0]), int(linha[1])


def situacao_do_produto(
    conexao: sqlite3.Connection, produto_id: int,
    inicio: str | None = None, fim: str | None = None,
) -> dict:
    """
    O retrato completo do estoque do produto no periodo.

    `disponivel` pode sair negativo: e o razao dizendo que ha mais poltrona
    prometida do que existia no papel -- esconder isso com um max(0, ...) e
    transformar o alerta mais importante do controle em silencio.
    """
    inicio = inicio or _hoje()
    fim = fim or _SEM_FIM

    total = total_do_produto(conexao, produto_id)
    locado, sem_janela = quantidade_reservada(
        conexao, produto_id, inicio, fim, SITUACOES_QUE_RESERVAM)
    negociando, _ = quantidade_reservada(
        conexao, produto_id, inicio, fim, SITUACOES_EM_NEGOCIACAO)

    return {
        "produto_id": produto_id,
        "total": total,
        "locado": locado,
        "sem_janela": sem_janela,
        "em_negociacao": negociando,
        "disponivel": total - locado,
        "configurado": total > 0,
        "periodo": {"inicio": inicio, "fim": fim},
    }


def resumo(conexao: sqlite3.Connection) -> list[dict]:
    """
    Um retrato por produto ativo, para a coluna da lista de Produtos.

    O periodo e o dia corrente -- e a pergunta que a lista responde ("o que
    esta fora agora"), e a tela de estoque de cada produto existe para as
    outras perguntas.
    """
    hoje = _hoje()
    produtos = conexao.execute(
        "SELECT id FROM produtos WHERE ativo = 1 ORDER BY descricao COLLATE NOCASE"
    ).fetchall()
    resumo = []
    for (produto_id,) in produtos:
        situacao = situacao_do_produto(conexao, produto_id, hoje, hoje)
        situacao.pop("periodo")
        resumo.append(situacao)
    return resumo


def movimentos_do_produto(
    conexao: sqlite3.Connection, produto_id: int, limite: int = 100,
) -> list[dict]:
    """O razao do produto, do lancamento mais recente para o mais antigo."""
    linhas = conexao.execute(
        """SELECT id, delta, tipo, motivo, criado_em
             FROM estoque_movimentos WHERE produto_id = ?
            ORDER BY id DESC LIMIT ?""",
        (produto_id, limite),
    ).fetchall()
    return [dict(linha) for linha in linhas]


def validar_movimento(conexao: sqlite3.Connection, dados: dict) -> dict:
    """
    Um movimento valido, ou a lista do que ele tem de errado.

    O sinal do delta e conferido contra o TIPO: 'aquisicao' de delta
    negativo e um texto mentindo sobre o que aconteceu, e o razao inteiro
    perde valor se aceitar isso calado.
    """
    erros: list[str] = []

    try:
        delta = int(dados.get("delta"))
    except (TypeError, ValueError):
        delta = 0
        erros.append("Quantidade deve ser um numero inteiro diferente de zero.")

    tipo = str(dados.get("tipo") or "").strip().lower()
    if tipo not in TIPOS_DE_MOVIMENTO:
        erros.append(f"Tipo deve ser um de: {', '.join(TIPOS_DE_MOVIMENTO)}.")

    if not erros:
        if delta == 0:
            erros.append("Quantidade deve ser diferente de zero.")
        elif tipo == "aquisicao" and delta < 0:
            erros.append("Aquisicao entra no estoque: use quantidade positiva.")
        elif tipo == "baixa" and delta > 0:
            erros.append("Baixa sai do estoque: use quantidade negativa.")

    motivo = str(dados.get("motivo") or "").strip()[:200]

    if erros:
        raise EstoqueInvalido(" ".join(erros))
    return {"delta": delta, "tipo": tipo, "motivo": motivo}


def lancar_movimento(
    conexao: sqlite3.Connection, produto_id: int, dados: dict,
) -> dict:
    """
    Grava um movimento no razao e devolve o retrato atualizado.

    Recusa estoque negativo: a partir daqui o numero aparece em telas e
    decisoes (a aprovacao de pedidos confere disponibilidade), e um total
    que mente sobre a fisica da loja e pior que um total ausente.
    """
    movimento = validar_movimento(conexao, dados)
    total = total_do_produto(conexao, produto_id)
    if total + movimento["delta"] < 0:
        raise EstoqueInvalido(
            "O movimento deixa o estoque negativo "
            f"({total} {movimento['delta']:+d}).")
    conexao.execute(
        """INSERT INTO estoque_movimentos (produto_id, delta, tipo, motivo)
           VALUES (?, ?, ?, ?)""",
        (produto_id, movimento["delta"], movimento["tipo"], movimento["motivo"]),
    )
    return movimento
