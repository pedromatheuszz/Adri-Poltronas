"""
Emissao de cobranca no Asaas, de forma idempotente.

O problema
----------
Emitir uma cobranca sao tres passos, e so o primeiro e o ultimo sao nossos:

    1. chamar o Asaas para criar a cobranca
    2. receber o id
    3. gravar o id no SQLite

Se o processo morrer entre 1 e 3 -- queda de energia, o app sendo fechado, a
resposta HTTP se perdendo no caminho --, a cobranca existe no Asaas e o
sistema nao sabe. A tela mostra "gerar cobranca" de novo, o operador clica, e
o cliente recebe DUAS cobrancas do mesmo valor. Nao havia nada impedindo:

* clique repetido no botao;
* duas requisicoes simultaneas sobre o mesmo pagamento;
* emissao sobre um pagamento que ja tinha `asaas_payment_id`;
* emissao sobre um pagamento ja recebido ou cancelado.

O banco ja tinha a infraestrutura para resolver isso -- as colunas
`asaas_external_reference` e `asaas_emissao_estado`, mais um indice unico
parcial sobre a referencia --, e nenhuma linha de codigo a usava.

A solucao
---------
Registrar a INTENCAO localmente antes de sair para a rede. A ordem passa a ser:

    1. reivindicar a emissao: gravar uma referencia unica nossa e marcar o
       estado como `iniciada`, num UPDATE condicional que so vence se ninguem
       reivindicou antes (e o compare-and-swap que resolve o clique duplo e a
       concorrencia de uma vez)
    2. chamar o Asaas, enviando essa referencia junto
    3. gravar o id devolvido e marcar `concluida`

Se algo quebrar no meio, a proxima tentativa encontra o estado `iniciada` com
uma referencia conhecida e PERGUNTA ao Asaas se ja existe cobranca com ela,
em vez de criar outra as cegas.

Estados possiveis de `asaas_emissao_estado`:

    ''          nunca se tentou emitir
    iniciada    intencao registrada, resultado desconhecido
    concluida   ha `asaas_payment_id` gravado
    falhou      o Asaas recusou de forma conhecida; a referencia fica, para a
                proxima tentativa reconciliar antes de emitir
"""
from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from contextlib import AbstractContextManager
import sqlite3

from erp.core.auditoria import registrar_evento

log = logging.getLogger("adri.emissao")

FabricaConexao = Callable[[], AbstractContextManager[sqlite3.Connection]]

ESTADO_INICIADA = "iniciada"
ESTADO_CONCLUIDA = "concluida"
ESTADO_FALHOU = "falhou"

# Estados a partir dos quais uma nova reivindicacao pode vencer. `iniciada`
# NAO esta aqui de proposito: quem encontra esse estado precisa reconciliar
# antes, nunca emitir por cima.
ESTADOS_REIVINDICAVEIS = ("", ESTADO_FALHOU)

# Cobranca so se emite sobre valor que ainda esta em aberto. Emitir sobre
# 'Recebido' cobraria de novo quem ja pagou.
STATUS_QUE_ACEITAM_EMISSAO = ("Pendente", "Atrasado")


class EmissaoJaEmCurso(Exception):
    """Outra requisicao reivindicou esta emissao e ainda nao terminou."""


class EmissaoNaoPermitida(Exception):
    """O pagamento nao esta em estado que aceite cobranca."""


def nova_referencia() -> str:
    """
    Identificador nosso, unico por tentativa de emissao.

    Vai junto na criacao da cobranca (`externalReference`) e e o que permite
    perguntar depois "voce ja criou uma cobranca para isto?".
    """
    return f"adri-{uuid.uuid4().hex}"


def reivindicar(conectar: FabricaConexao, pagamento_id: int) -> tuple[str, dict]:
    """
    Marca a intencao de emitir e devolve (referencia, pagamento).

    O UPDATE e condicional: so vence quem encontrar o estado ainda livre. Dois
    cliques simultaneos produzem um vencedor e um `EmissaoJaEmCurso` -- que e
    exatamente o que se quer, porque o segundo nao tem como saber se o
    primeiro ja criou a cobranca.

    Levanta `EmissaoNaoPermitida` quando o pagamento nao aceita cobranca, e
    `EmissaoJaEmCurso` quando outra reivindicacao esta em aberto.
    """
    with conectar() as conexao:
        linha = conexao.execute(
            "SELECT * FROM pagamentos WHERE id=?", (pagamento_id,)
        ).fetchone()
        if not linha:
            raise EmissaoNaoPermitida("Pagamento nao encontrado.")

        pagamento = dict(linha)
        if pagamento.get("status") not in STATUS_QUE_ACEITAM_EMISSAO:
            raise EmissaoNaoPermitida(
                f"Nao e possivel gerar cobranca para um pagamento "
                f"'{pagamento.get('status')}'."
            )

        referencia = nova_referencia()
        cursor = conexao.execute(
            "UPDATE pagamentos SET asaas_external_reference=?, asaas_emissao_estado=? "
            "WHERE id=? AND COALESCE(asaas_emissao_estado,'') IN (?, ?)",
            (referencia, ESTADO_INICIADA, pagamento_id, *ESTADOS_REIVINDICAVEIS),
        )
        if cursor.rowcount == 0:
            raise EmissaoJaEmCurso(
                "Ja ha uma emissao em andamento para esta cobranca."
            )

        registrar_evento(
            conexao,
            acao="financeiro.cobranca.emissao_iniciada",
            entidade="pagamento",
            entidade_id=pagamento_id,
            valores_novos={"asaas_external_reference": referencia},
        )
        pagamento["asaas_external_reference"] = referencia
        pagamento["asaas_emissao_estado"] = ESTADO_INICIADA
        return referencia, pagamento


def concluir(conectar: FabricaConexao, pagamento_id: int, asaas_payment_id: str,
             **campos_extras) -> None:
    """Grava o id devolvido pelo Asaas e fecha a emissao."""
    with conectar() as conexao:
        atribuicoes = ["asaas_payment_id=?", "asaas_emissao_estado=?"]
        valores: list = [asaas_payment_id, ESTADO_CONCLUIDA]
        for campo, valor in campos_extras.items():
            atribuicoes.append(f"{campo}=?")
            valores.append(valor)
        valores.append(pagamento_id)
        conexao.execute(
            f"UPDATE pagamentos SET {', '.join(atribuicoes)} WHERE id=?", valores
        )
        registrar_evento(
            conexao,
            acao="financeiro.cobranca.emitida",
            entidade="pagamento",
            entidade_id=pagamento_id,
            valores_novos={"asaas_payment_id": asaas_payment_id},
        )


def falhar(conectar: FabricaConexao, pagamento_id: int, motivo: str) -> None:
    """
    Marca a tentativa como falha, PRESERVANDO a referencia.

    A referencia fica de proposito: se a falha foi de rede, a cobranca pode
    ter sido criada mesmo assim, e a proxima tentativa precisa dela para
    perguntar antes de emitir.
    """
    with conectar() as conexao:
        conexao.execute(
            "UPDATE pagamentos SET asaas_emissao_estado=? WHERE id=?",
            (ESTADO_FALHOU, pagamento_id),
        )
        registrar_evento(
            conexao,
            acao="financeiro.cobranca.emissao_falhou",
            entidade="pagamento",
            entidade_id=pagamento_id,
            valores_novos={"motivo": motivo[:200]},
        )


def reconciliar_emissao_em_aberto(conectar: FabricaConexao, pagamento: dict,
                                  cliente_asaas) -> dict | None:
    """
    Descobre se uma emissao anterior chegou a criar cobranca.

    Chamado quando o pagamento esta em `iniciada` (ou em `falhou` com
    referencia): pergunta ao Asaas se existe cobranca com a nossa referencia.

    Devolve:
      * o dict da cobranca, quando ela existe -- e ja fecha a emissao no banco;
      * `None`, quando comprovadamente nao existe: emitir agora e seguro;
      * levanta `EmissaoJaEmCurso` quando a propria consulta falhou. Nesse caso
        NAO se sabe, e emitir seria justamente o risco que isto evita.
    """
    referencia = (pagamento.get("asaas_external_reference") or "").strip()
    if not referencia:
        return None

    resultado = cliente_asaas.buscar_por_referencia_externa(referencia)
    if isinstance(resultado, dict) and resultado.get("_erro"):
        raise EmissaoJaEmCurso(
            "Nao foi possivel confirmar com o Asaas se a cobranca anterior "
            "foi criada. Tente novamente em instantes."
        )
    if not resultado:
        return None

    asaas_payment_id = resultado.get("id", "")
    if asaas_payment_id:
        log.info(
            "[EMISSAO] Cobranca %s recuperada pela referencia %s",
            asaas_payment_id, referencia,
        )
        concluir(conectar, int(pagamento["id"]), asaas_payment_id)
    return resultado
