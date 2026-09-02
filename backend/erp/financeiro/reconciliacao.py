"""
Conciliacao ativa das cobrancas com o Asaas.

Por que isto precisa existir
----------------------------
O sistema confiava no webhook do Asaas para saber que uma cobranca foi paga.
Numa instalacao normal, esse webhook NUNCA chega: o Flask escuta em
127.0.0.1:5000, e um servidor na internet nao alcanca o loopback da maquina
do usuario. Nao ha tunel, relay nem endereco publico no projeto.

O efeito pratico era um sistema que parecia integrado e nao era. O cliente
pagava o Pix, o dinheiro entrava na conta do Asaas, e a cobranca continuava
"Pendente" no ERP ate alguem confirmar na mao -- confirmacao que, ate aqui,
nem verificava se o pagamento realmente aconteceu.

Expor a porta 5000 para a internet resolveria o webhook e abriria a aplicacao
inteira junto, incluindo todas as rotas locais. Nao e uma troca aceitavel.

A solucao
---------
Inverter a direcao: em vez de esperar o Asaas nos procurar, nos perguntamos a
ele. Uma consulta de saida atravessa qualquer firewall e nao expoe nada.

O webhook continua no lugar e continua sendo o caminho mais rapido para quem
tiver infraestrutura para recebe-lo (um relay publico autenticado, por
exemplo). A conciliacao e o que faz o sistema funcionar sem ela.

Idempotencia
------------
Tudo passa por `aplicar_evento_asaas`, que so escreve quando o status muda de
verdade e registra o evento na auditoria. Rodar a conciliacao dez vezes
seguidas produz o mesmo resultado que roda-la uma vez.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from contextlib import AbstractContextManager
import sqlite3

from erp.financeiro.servico_pagamentos import aplicar_evento_asaas

log = logging.getLogger("adri.reconciliacao")

FabricaConexao = Callable[[], AbstractContextManager[sqlite3.Connection]]

# Como o vocabulario do Asaas se traduz para o nosso.
#
# O que NAO esta aqui e tao importante quanto o que esta: status que nao
# reconhecemos sao ignorados em vez de virarem um palpite. Um mapeamento
# errado num campo financeiro e pior do que um campo desatualizado.
TRADUCAO_DE_STATUS = {
    "RECEIVED": "Recebido",
    "CONFIRMED": "Recebido",
    "RECEIVED_IN_CASH": "Recebido",
    "OVERDUE": "Atrasado",
    "PENDING": "Pendente",
    "AWAITING_RISK_ANALYSIS": "Pendente",
    "DELETED": "Cancelado",
    "REFUNDED": "Cancelado",
    "REFUND_REQUESTED": "Cancelado",
    "CHARGEBACK_REQUESTED": "Cancelado",
    "CHARGEBACK_DISPUTE": "Cancelado",
    "AWAITING_CHARGEBACK_REVERSAL": "Cancelado",
}

# Status locais que ainda valem a pena consultar. Uma cobranca 'Recebido' ou
# 'Cancelado' e terminal do nosso lado -- perguntar por ela seria gastar
# chamada de API para confirmar o que ja se sabe.
STATUS_EM_ABERTO = ("Pendente", "Atrasado")

# Teto por rodada. A conciliacao roda quando o operador abre a aba de
# pagamentos, e uma chamada de rede por cobranca com centenas de cobrancas em
# aberto travaria a tela. O que passar do teto entra na proxima rodada.
LIMITE_POR_RODADA = 50


def cobrancas_em_aberto(conectar: FabricaConexao, limite: int = LIMITE_POR_RODADA) -> list[dict]:
    """
    Cobrancas que tem id no Asaas e ainda nao terminaram do nosso lado.

    Ordenadas pelo vencimento mais antigo: e onde uma divergencia doi mais
    (cobranca vencida que na verdade foi paga) e o que o operador olha
    primeiro.
    """
    marcadores = ",".join("?" for _ in STATUS_EM_ABERTO)
    with conectar() as conexao:
        linhas = conexao.execute(
            f"SELECT id, asaas_payment_id, status, valor, data_vencimento "
            f"FROM pagamentos "
            f"WHERE asaas_payment_id IS NOT NULL AND asaas_payment_id != '' "
            f"AND status IN ({marcadores}) "
            f"ORDER BY data_vencimento ASC LIMIT ?",
            (*STATUS_EM_ABERTO, limite),
        ).fetchall()
    return [dict(linha) for linha in linhas]


def reconciliar(conectar: FabricaConexao, cliente_asaas,
                limite: int = LIMITE_POR_RODADA) -> dict:
    """
    Pergunta ao Asaas o estado atual de cada cobranca em aberto e aplica o que
    tiver mudado.

    Devolve um resumo do que aconteceu. `falhas` conta cobrancas cuja consulta
    nao respondeu -- elas ficam como estao e entram na proxima rodada, porque
    um erro de rede nao e informacao sobre o pagamento.
    """
    pendentes = cobrancas_em_aberto(conectar, limite)
    resumo = {
        "consultadas": len(pendentes),
        "atualizadas": 0,
        "falhas": 0,
        "mudancas": [],
    }

    for cobranca in pendentes:
        asaas_payment_id = cobranca["asaas_payment_id"]
        resposta = cliente_asaas.obter_status_pagamento(asaas_payment_id)
        if not isinstance(resposta, dict) or resposta.get("_erro"):
            resumo["falhas"] += 1
            log.warning(
                "[CONCILIACAO] Nao foi possivel consultar %s: %s",
                asaas_payment_id, resposta,
            )
            continue

        status_asaas = (resposta.get("status") or "").upper()
        status_local = TRADUCAO_DE_STATUS.get(status_asaas)
        if not status_local:
            log.info(
                "[CONCILIACAO] Status desconhecido '%s' em %s; ignorado.",
                status_asaas, asaas_payment_id,
            )
            continue
        if status_local == cobranca["status"]:
            continue

        alterou = aplicar_evento_asaas(
            conectar,
            asaas_payment_id,
            status_local,
            preencher_data_pagamento=(status_local == "Recebido"),
        )
        if alterou:
            resumo["atualizadas"] += 1
            resumo["mudancas"].append({
                "pagamento_id": cobranca["id"],
                "de": cobranca["status"],
                "para": status_local,
            })
            log.info(
                "[CONCILIACAO] Pagamento %s: %s -> %s",
                cobranca["id"], cobranca["status"], status_local,
            )

    return resumo


def confirmar_com_o_gateway(conectar: FabricaConexao, cliente_asaas,
                            pagamento: dict) -> tuple[bool, str]:
    """
    Confere UMA cobranca antes de marca-la como recebida na mao.

    A confirmacao manual existia sem nenhuma verificacao: um clique marcava
    'Recebido' mesmo com a cobranca aberta no Asaas, e o ERP passava a
    declarar uma receita que ninguem tinha recebido.

    Devolve (pode_confirmar, motivo). Quando a cobranca nem tem id no Asaas --
    dinheiro, transferencia combinada por fora --, confirmar na mao e
    legitimo: nao ha gateway com o que conferir.
    """
    asaas_payment_id = (pagamento.get("asaas_payment_id") or "").strip()
    if not asaas_payment_id:
        return True, "sem cobranca no gateway"

    resposta = cliente_asaas.obter_status_pagamento(asaas_payment_id)
    if not isinstance(resposta, dict) or resposta.get("_erro"):
        return False, (
            "Nao foi possivel confirmar com o Asaas o estado desta cobranca. "
            "Tente novamente em instantes."
        )

    status_asaas = (resposta.get("status") or "").upper()
    if TRADUCAO_DE_STATUS.get(status_asaas) == "Recebido":
        return True, status_asaas

    return False, (
        f"A cobranca continua '{status_asaas}' no Asaas. Se o pagamento foi "
        f"feito por fora do gateway, cancele esta cobranca e registre um "
        f"recebimento avulso."
    )
