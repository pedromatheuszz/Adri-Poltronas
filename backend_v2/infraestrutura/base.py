"""Base dos repositorios: todos falam com a conexao da unidade de trabalho."""
from __future__ import annotations

import sqlite3


class Repositorio:
    """
    Um repositorio NAO abre conexao: recebe a da transacao em curso.

    E o que garante que dois repositorios usados no mesmo caso de uso -- gravar
    o pedido e baixar o estoque -- entrem ou saiam juntos. No v1 cada funcao
    abria a sua, e um caso de uso a meio caminho ficava a meio caminho.
    """

    tabela: str = ""

    def __init__(self, conexao: sqlite3.Connection):
        self.conexao = conexao

    # -- utilitarios ---------------------------------------------------------
    def _um(self, sql: str, parametros=()) -> dict | None:
        linha = self.conexao.execute(sql, parametros).fetchone()
        return dict(linha) if linha else None

    def _varios(self, sql: str, parametros=()) -> list[dict]:
        return [dict(linha) for linha in self.conexao.execute(sql, parametros).fetchall()]

    def _escalar(self, sql: str, parametros=()):
        linha = self.conexao.execute(sql, parametros).fetchone()
        return linha[0] if linha else None

    def _inserir(self, tabela: str, campos: dict) -> int:
        colunas = ', '.join(campos)
        marcadores = ', '.join('?' * len(campos))
        cursor = self.conexao.execute(
            'INSERT INTO %s (%s) VALUES (%s)' % (tabela, colunas, marcadores),
            list(campos.values()),
        )
        return int(cursor.lastrowid)

    def _atualizar(self, tabela: str, identificador: int, campos: dict) -> int:
        if not campos:
            return 0
        atribuicoes = ', '.join('%s=?' % coluna for coluna in campos)
        cursor = self.conexao.execute(
            'UPDATE %s SET %s WHERE id=?' % (tabela, atribuicoes),
            list(campos.values()) + [identificador],
        )
        return cursor.rowcount

    # -- por id --------------------------------------------------------------
    def buscar(self, identificador: int) -> dict | None:
        return self._um('SELECT * FROM %s WHERE id=?' % self.tabela, (identificador,))
