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

A solucao, e por que ela tem tres passos
----------------------------------------
Quem envia carrega uma chave unica por operacao (`Idempotency-Key`, gerada uma
vez, no momento em que a operacao entra na fila -- nao a cada tentativa).

A primeira versao deste modulo registrava a resposta DEPOIS de a rota
executar, em outra transacao. A janela entre as duas e pequena e real: um
processo encerrado ali deixa a escrita feita e a chave sem registro, e o
proximo reenvio duplica -- exatamente o que a chave existe para impedir.

Juntar as duas coisas numa transacao so exigiria que todas as rotas
recebessem a conexao de fora. A saida e a mesma que `erp/financeiro/emissao.py`
usa para a cobranca: registrar a INTENCAO antes de agir.

    reservar  ->  a rota executa  ->  concluir

* Cair entre reservar e executar: chave reservada, nada escrito. A repeticao
  ve "em andamento" e recua.
* Cair entre executar e concluir: escrita feita, chave reservada. A repeticao
  tambem recua -- e nao duplica.

Em nenhum dos dois a operacao acontece duas vezes, que e a propriedade que
importa. O preco e uma reserva orfa, que a poda por idade recolhe.

A impressao do corpo
--------------------
A chave sozinha nao basta. Reaproveitar a mesma chave para OUTRA operacao
devolveria, em silencio, a resposta da primeira -- um erro de cliente virando
dado errado sem nenhum sinal. Por isso a reserva guarda um hash de
metodo + rota + corpo, e uma chave que volta com corpo diferente e recusada.

Escopo
------
So respostas de SUCESSO viram lembranca definitiva. Um 400 de validacao nao
precisa ser lembrado -- reenviar produz o mesmo 400, sem efeito colateral --, e
guardar erros impediria a fila de tentar de novo depois que a causa fosse
corrigida.
"""
from __future__ import annotations

import hashlib
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

# Estados de uma chave.
RESERVADA = "reservada"
CONCLUIDA = "concluida"

# Resultados possiveis de `reservar`, para quem chama decidir o que fazer.
LIVRE = "livre"            # a chave e nova; pode executar
REPETIDA = "repetida"      # ja concluida; devolver a resposta guardada
EM_ANDAMENTO = "em_andamento"  # reservada e sem resposta; recuar
CONFLITO = "conflito"      # mesma chave, corpo diferente


def chave_valida(chave: str | None) -> bool:
    if not chave:
        return False
    chave = chave.strip()
    return 0 < len(chave) <= TAMANHO_MAXIMO_DA_CHAVE


def impressao_da_requisicao(metodo: str, rota: str, corpo: bytes | str | None) -> str:
    """
    Hash de metodo + rota + corpo.

    E o que distingue "a mesma operacao, reenviada" de "outra operacao com a
    chave reutilizada por engano". Sem isso, a segunda receberia a resposta da
    primeira e ninguem notaria.
    """
    if isinstance(corpo, str):
        corpo = corpo.encode("utf-8")
    material = b"|".join([
        (metodo or "").upper().encode("utf-8"),
        (rota or "").encode("utf-8"),
        corpo or b"",
    ])
    return hashlib.sha256(material).hexdigest()


def reservar(conectar: FabricaConexao, chave: str, rota: str, metodo: str,
             impressao: str) -> tuple[str, tuple[int, dict] | None]:
    """
    Tenta reservar a chave. Devolve (situacao, resposta_guardada).

    `situacao` e um dos quatro valores acima. `resposta_guardada` so vem
    preenchida quando a situacao e `REPETIDA`.

    O INSERT e condicional por chave primaria: duas requisicoes simultaneas
    produzem uma reserva e um conflito, sem necessidade de lock explicito.
    """
    with conectar() as conexao:
        try:
            conexao.execute(
                "INSERT INTO operacoes_idempotentes "
                "(chave, rota, metodo, estado, impressao) VALUES (?, ?, ?, ?, ?)",
                (chave, rota, metodo, RESERVADA, impressao),
            )
            return LIVRE, None
        except sqlite3.IntegrityError:
            pass  # ja existe: a analise vem abaixo
        except sqlite3.Error:
            # Banco sem a tabela (schema de emergencia, instalacao antiga):
            # perder idempotencia e ruim, recusar a escrita seria pior.
            log.warning("[IDEMPOTENCIA] Tabela indisponivel; seguindo sem lembranca.")
            return LIVRE, None

        linha = conexao.execute(
            "SELECT estado, status, corpo, impressao "
            "FROM operacoes_idempotentes WHERE chave=?",
            (chave,),
        ).fetchone()

    if linha is None:
        return LIVRE, None

    # Impressao ausente e uma linha gravada pela versao anterior do modulo,
    # que nao a registrava. Nao da para conferir, e inventar um conflito ali
    # recusaria reenvios legitimos de uma fila que ja estava em curso.
    guardada = linha["impressao"]
    if guardada and guardada != impressao:
        return CONFLITO, None

    if linha["estado"] == RESERVADA:
        return EM_ANDAMENTO, None

    try:
        return REPETIDA, (int(linha["status"]), json.loads(linha["corpo"]))
    except (ValueError, TypeError):
        # Linha corrompida: melhor deixar executar de novo do que devolver
        # uma resposta que nao se consegue ler.
        return LIVRE, None


def concluir(conectar: FabricaConexao, chave: str, status: int, corpo: dict) -> None:
    """Fecha a reserva com a resposta que a rota deu."""
    with conectar() as conexao:
        try:
            conexao.execute(
                "UPDATE operacoes_idempotentes "
                "   SET estado=?, status=?, corpo=? "
                " WHERE chave=?",
                (CONCLUIDA, int(status), json.dumps(corpo, ensure_ascii=False), chave),
            )
        except sqlite3.Error as erro:
            log.warning("[IDEMPOTENCIA] Nao concluiu a chave %s: %s", chave, erro)


def liberar(conectar: FabricaConexao, chave: str) -> None:
    """
    Descarta a reserva.

    Usado quando a rota respondeu ERRO: a chave nao pode ficar reservada, ou o
    reenvio depois de corrigida a causa encontraria "em andamento" para
    sempre. E tambem nao pode ser concluida, porque erro nao e lembranca.
    """
    with conectar() as conexao:
        try:
            conexao.execute(
                "DELETE FROM operacoes_idempotentes WHERE chave=? AND estado=?",
                (chave, RESERVADA),
            )
        except sqlite3.Error as erro:
            log.warning("[IDEMPOTENCIA] Nao liberou a chave %s: %s", chave, erro)


def limpar_antigas(conectar: FabricaConexao, dias: int = DIAS_DE_RETENCAO) -> int:
    """
    Descarta lembrancas velhas -- e tambem reservas orfas, deixadas por um
    processo que morreu no meio. Chamado no boot; nunca levanta.
    """
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
