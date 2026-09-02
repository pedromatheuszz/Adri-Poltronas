"""
Idempotencia por chave, para as escritas que vem da fila offline.

O problema
----------
A fila offline reenvia uma operacao sempre que a anterior nao confirmou. Mas
"nao confirmou" e ambiguo: pode ser que o servidor nunca tenha recebido, ou
que tenha recebido, gravado, e a resposta ter se perdido no caminho de volta.
Do lado do navegador as duas situacoes sao identicas -- um `fetch` que rejeita.

Sem nada que distinga uma coisa da outra, reenviar um POST de criacao produz
DOIS clientes iguais no banco. E o operador so descobre depois, olhando a
lista.

A solucao
---------
Quem envia carrega uma chave unica por operacao (`Idempotency-Key`, gerada uma
vez, no momento em que a operacao entra na fila -- nao a cada tentativa). O
servidor guarda a resposta que deu para aquela chave. Se a mesma chave voltar,
devolve a MESMA resposta em vez de executar de novo.

E o mesmo mecanismo que gateways de pagamento usam, e pelo mesmo motivo: numa
rede nao confiavel, a unica forma de repetir com seguranca e o servidor
lembrar do que ja fez.

Escopo
------
So se registram respostas de SUCESSO. Um 400 de validacao nao precisa ser
lembrado -- reenviar produz o mesmo 400, sem efeito colateral --, e guardar
erros faria a tabela crescer com o que nao interessa.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from collections.abc import Callable
from contextlib import AbstractContextManager

log = logging.getLogger("adri.idempotencia")

FabricaConexao = Callable[[], AbstractContextManager[sqlite3.Connection]]

NOME_DO_HEADER = "Idempotency-Key"

# Uma chave e um UUID em hexadecimal, com ou sem tracos, as vezes prefixada.
# O teto existe para uma chave absurda nao virar uma linha absurda no banco.
TAMANHO_MAXIMO_DA_CHAVE = 100

# Por quanto tempo a lembranca vale. A fila offline nao guarda operacao por
# semanas -- se guardou, o cenario ja e outro e a repeticao deixa de ser um
# reenvio automatico para virar uma decisao. Sete dias cobrem com folga uma
# viagem, um fim de semana ou um notebook esquecido ligado.
DIAS_DE_RETENCAO = 7


def chave_valida(chave: str | None) -> bool:
    if not chave:
        return False
    chave = chave.strip()
    return 0 < len(chave) <= TAMANHO_MAXIMO_DA_CHAVE


def resposta_registrada(conectar: FabricaConexao, chave: str) -> tuple[int, dict] | None:
    """Resposta ja dada para esta chave, ou None se e a primeira vez."""
    with conectar() as conexao:
        try:
            linha = conexao.execute(
                "SELECT status, corpo FROM operacoes_idempotentes WHERE chave=?",
                (chave,),
            ).fetchone()
        except sqlite3.Error:
            # Banco sem a tabela (fallback de emergencia, instalacao antiga):
            # perder idempotencia e ruim, recusar a escrita seria pior.
            log.warning("[IDEMPOTENCIA] Tabela indisponivel; seguindo sem lembranca.")
            return None
    if not linha:
        return None
    try:
        return int(linha["status"]), json.loads(linha["corpo"])
    except (ValueError, TypeError):
        return None


def registrar(conectar: FabricaConexao, chave: str, rota: str, metodo: str,
              status: int, corpo: dict) -> None:
    """Guarda a resposta dada, para que a repeticao devolva a mesma coisa."""
    with conectar() as conexao:
        try:
            conexao.execute(
                "INSERT OR REPLACE INTO operacoes_idempotentes "
                "(chave, rota, metodo, status, corpo) VALUES (?, ?, ?, ?, ?)",
                (chave, rota, metodo, int(status), json.dumps(corpo, ensure_ascii=False)),
            )
        except sqlite3.Error as erro:
            log.warning("[IDEMPOTENCIA] Nao registrou a chave %s: %s", chave, erro)


def limpar_antigas(conectar: FabricaConexao, dias: int = DIAS_DE_RETENCAO) -> int:
    """Descarta lembrancas velhas. Chamado no boot; nunca levanta."""
    with conectar() as conexao:
        try:
            cursor = conexao.execute(
                "DELETE FROM operacoes_idempotentes "
                "WHERE criado_em < datetime('now', 'localtime', ?)",
                (f"-{int(dias)} days",),
            )
            return cursor.rowcount
        except sqlite3.Error:
            return 0
