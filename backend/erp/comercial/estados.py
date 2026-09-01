"""
Maquina de estados do pedido de venda.

Por que uma tabela e nao uma sequencia de `if`: sem um lugar unico que declare
o que pode virar o que, cada rota decide sozinha o que aceita -- e alguem
acaba faturando um pedido cancelado, ou aprovando duas vezes o mesmo
documento. O v1 hoje sofre exatamente disso nos pagamentos e nas entregas, que
tem status em texto livre validado caso a caso.

O ciclo, para uma fabrica sob encomenda:

    rascunho --> aberto --> aprovado --> faturado
        |          |           |
        +----------+-----------+--> cancelado

* **rascunho**  o pedido esta sendo montado; itens entram e saem
* **aberto**    apresentado ao cliente, aguardando o aceite
* **aprovado**  cliente aceitou; a producao pode comecar e a entrega pode ser
                agendada
* **faturado**  as parcelas a receber foram emitidas -- terminal, porque a
                partir daqui existe dinheiro cobrado do outro lado
* **cancelado** terminal

Colhido de `backend_v2/aplicacao/vendas.py` antes da remocao daquele backend.
"""
from __future__ import annotations

RASCUNHO = "rascunho"
ABERTO = "aberto"
APROVADO = "aprovado"
FATURADO = "faturado"
CANCELADO = "cancelado"

SITUACOES = (RASCUNHO, ABERTO, APROVADO, FATURADO, CANCELADO)

# De onde para onde um pedido pode ir. Conjunto vazio = estado terminal.
TRANSICOES: dict[str, frozenset[str]] = {
    RASCUNHO: frozenset({ABERTO, CANCELADO}),
    ABERTO: frozenset({APROVADO, CANCELADO}),
    APROVADO: frozenset({FATURADO, CANCELADO}),
    # Terminal: as parcelas a receber ja foram emitidas. Desfazer exige
    # estorno explicito, nao uma volta de status.
    FATURADO: frozenset(),
    CANCELADO: frozenset(),
}

# Itens so podem ser mexidos enquanto o pedido nao foi aceito pelo cliente.
SITUACOES_EDITAVEIS = frozenset({RASCUNHO, ABERTO})

# A entrega so faz sentido depois do aceite -- antes disso nao ha o que levar.
SITUACOES_QUE_ACEITAM_ENTREGA = frozenset({APROVADO, FATURADO})


class TransicaoInvalida(Exception):
    """Mudanca de situacao que a maquina de estados nao permite."""


def pode_transicionar(origem: str, destino: str) -> bool:
    return destino in TRANSICOES.get(origem, frozenset())


def exigir_transicao(origem: str, destino: str, identificacao: str = "") -> None:
    """Levanta `TransicaoInvalida` quando o caminho nao existe."""
    if pode_transicionar(origem, destino):
        return
    alvo = f"O pedido {identificacao}" if identificacao else "O pedido"
    raise TransicaoInvalida(
        f"{alvo} esta em '{origem}' e nao pode ir para '{destino}'."
    )


def e_editavel(situacao: str) -> bool:
    return situacao in SITUACOES_EDITAVEIS


def aceita_entrega(situacao: str) -> bool:
    return situacao in SITUACOES_QUE_ACEITAM_ENTREGA


def proximos_passos(situacao: str) -> tuple[str, ...]:
    """
    Destinos validos a partir da situacao atual.

    A tela usa isto para decidir quais botoes mostrar, em vez de repetir a
    regra em JavaScript e arriscar divergir do backend.
    """
    return tuple(sorted(TRANSICOES.get(situacao, frozenset())))
