"""
Relatorio financeiro: as parcelas a receber, lidas como o contador le.

Ate aqui as parcelas so existiam DENTRO do pedido -- e o faturamento de um
mes inteiro ficava espalhado por N telas, cada uma aberta a mao. Relatorio
e a mesma leitura, reunida: quem deve, quanto, para quando, e o que ja
entrou.

Tres decisoes que valem registro:

* A fonte e a tabela `pagamentos` inteira, nao so o que nasceu de pedido.
  As parcelas orfas (lançadas pelo cadastro avulso que existia antes da
  1.5.0) sao dinheiro real a receber, e um relatorio financeiro que as
  omite mente por omissoa. O numero do pedido vem por LEFT JOIN e aparece
  vazio nelas -- a coluna diz a verdade sobre o vinculo.

* "Em atraso" e DERIVADO do vencimento, como em todo o resto do sistema:
  status gravado responde o que o operador declarou; o calendario responde
  o que a data diz. O filtro `atrasadas` e a unica forma de pedir isso em
  uma consulta.

* O resumo e calculado SOBRE AS LINHAS FILTRADAS, nunca numa segunda
  consulta: resumo e tabela que divergem e o defeito que faz o operador
  parar de confiar em ambos.
"""
from __future__ import annotations

import datetime
import sqlite3

from erp.core import dinheiro

# Valor especial de filtro que significa "so as que passaram do vencimento".
FILTRO_ATRASADAS = "atrasadas"

SITUACOES_DE_FILTRO = ("", "Pendente", "Recebido", "Cancelado", FILTRO_ATRASADAS)


class FiltroInvalido(ValueError):
    """Filtro de relatorio que nao diz o que o operador quis perguntar."""


def _hoje() -> str:
    return datetime.date.today().isoformat()


def validar_filtro(de: str, ate: str, situacao: str) -> tuple[str, str, str]:
    """
    Confere o que veio pela query string, ou lista o que ele tem de errado.

    Data unica vale: `de` sozinho vira periodo de um dia. O inverso (`ate`
    sem `de`) nao vale -- "ate quando" sem "desde quando" nao e pergunta
    financeira, e provavelmente e erro de digitacao.
    """
    de = (de or "").strip()
    ate = (ate or "").strip()
    situacao = (situacao or "").strip()

    if situacao and situacao not in SITUACOES_DE_FILTRO:
        raise FiltroInvalido(
            f"Situacao invalida. Use uma de: {', '.join(s for s in SITUACOES_DE_FILTRO if s)}."
        )

    if de:
        _exigir_data(de, "Data inicial")
    if ate:
        _exigir_data(ate, "Data final")
    if de and ate and ate < de:
        raise FiltroInvalido("A data final nao pode vir antes da inicial.")
    if ate and not de:
        raise FiltroInvalido("Informe a data inicial junto com a final.")
    return de, ate, situacao


def _exigir_data(texto: str, nome: str) -> None:
    try:
        datetime.date.fromisoformat(texto)
    except ValueError:
        raise FiltroInvalido(f"{nome} invalida. Use o formato AAAA-MM-DD.") from None


def parcelas(conexao: sqlite3.Connection, de: str = "", ate: str = "",
             situacao: str = "") -> list[dict]:
    """
    As parcelas que atendem ao filtro, da que vence primeiro para a ultima.

    O atraso nunca e gravado: e recalculado aqui, na leitura, contra o dia
    corrente -- um relatorio que dependesse de uma rotina noturna para
    marcar atraso mentiria ate a rotina rodar.
    """
    de, ate, situacao = validar_filtro(de, ate, situacao)

    sql = (
        "SELECT pg.*, pd.numero AS pedido_numero "  # noqa: S608 - fragmentos vem de literais do proprio modulo
        "FROM pagamentos pg LEFT JOIN pedidos pd ON pd.id = pg.pedido_id "
        "WHERE 1=1"
    )
    parametros: list = []

    if de:
        # Data unica: dia inteiro, e nao "a partir da meia-noite dele".
        sql += " AND pg.data_vencimento >= ?"
        parametros.append(de)
        sql += " AND pg.data_vencimento <= ?"
        parametros.append(ate or de)
    if situacao == FILTRO_ATRASADAS:
        sql += " AND pg.status = 'Pendente' AND pg.data_vencimento != '' AND pg.data_vencimento < ?"
        parametros.append(_hoje())
    elif situacao:
        sql += " AND pg.status = ?"
        parametros.append(situacao)

    sql += " ORDER BY pg.data_vencimento, pg.id"
    linhas = conexao.execute(sql, parametros).fetchall()

    hoje = _hoje()
    resultado = []
    for linha in linhas:
        parcela = dict(linha)
        parcela["em_atraso"] = bool(
            parcela.get("status") == "Pendente"
            and parcela.get("data_vencimento")
            and str(parcela["data_vencimento"]) < hoje
        )
        resultado.append(parcela)
    return resultado


def _somar(registros: list[dict], predicate) -> tuple[int, int]:
    """(centavos, quantidade) das parcelas que passam no predicado."""
    selecionadas = [r for r in registros if predicate(r)]
    total = sum(int(r.get("valor_centavos") or 0) for r in selecionadas)
    return total, len(selecionadas)


def resumir(registros: list[dict]) -> dict:
    """
    O bloco de totais do relatorio, calculado sobre as MESMAS linhas.

    `atrasado` e subconjunto de `a_receber`: uma parcela vencida continua
    sendo dinheiro a entrar, e o relatorio que a listasse nas duas caixas
    como se fossem independentes faria o total nao fechar com a soma.
    """
    a_receber_centavos, a_receber_qtd = _somar(
        registros, lambda r: r.get("status") == "Pendente")
    atrasado_centavos, atrasado_qtd = _somar(
        registros, lambda r: r.get("em_atraso"))
    recebido_centavos, recebido_qtd = _somar(
        registros, lambda r: r.get("status") == "Recebido")

    return {
        "quantidade": len(registros),
        "a_receber": dinheiro.serializar(a_receber_centavos),
        "a_receber_qtd": a_receber_qtd,
        "atrasado": dinheiro.serializar(atrasado_centavos),
        "atrasado_qtd": atrasado_qtd,
        "recebido": dinheiro.serializar(recebido_centavos),
        "recebido_qtd": recebido_qtd,
    }


def para_planilha(registros: list[dict]) -> tuple:
    """
    Linhas prontas para `planilha.construir_planilha`.

    Dinheiro sai formatado como texto, nao como numero: a convencao do
    projeto e centavo inteiro ate a borda, e um float de centavos numa
    celula e exatamente a imprecisao binaria que `dinheiro.py` existe para
    evitar.
    """
    saida = []
    for r in registros:
        situacao = r.get("status") or ""
        if r.get("em_atraso"):
            situacao = "Pendente (em atraso)"
        saida.append({
            "vencimento": r.get("data_vencimento") or "",
            "cliente": r.get("cliente_nome") or "",
            "pedido": r.get("pedido_numero") or "",
            "parcela": (
                f"{r.get('parcela') or ''}/{r.get('total_parcelas') or ''}"
                if r.get("pedido_id") else ""
            ),
            "valor": dinheiro.formatar(int(r.get("valor_centavos") or 0)),
            "situacao": situacao,
            "pago_em": r.get("data_pagamento") or "",
            "forma": r.get("tipo_pagamento") or "",
        })
    return saida
