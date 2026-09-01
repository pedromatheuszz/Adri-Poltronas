"""
Unidade de Trabalho: uma transacao por caso de uso.

No v1 cada funcao de `database.py` abria a propria conexao. Um caso de uso que
tocava duas tabelas -- gerar cobranca gravava o pagamento numa transacao e o
vinculo com o Asaas em outra -- podia terminar pela metade, e nao havia como
desfazer. Aqui o servico recebe UMA unidade, todos os repositorios compartilham
a mesma conexao, e ou tudo entra ou nada entra. A auditoria vai junto, na mesma
transacao: registro de negocio e trilha nunca divergem.
"""
from __future__ import annotations

import sqlite3


class UnidadeDeTrabalho:
    def __init__(self, fabrica_conexao):
        self._fabrica = fabrica_conexao
        self.conexao: sqlite3.Connection | None = None
        self._repositorios: dict = {}

    # -- ciclo de vida -------------------------------------------------------
    def __enter__(self) -> "UnidadeDeTrabalho":
        self.conexao = self._fabrica()
        # BEGIN explicito: sem isso o sqlite3 do Python so abre transacao em
        # INSERT/UPDATE/DELETE, e um SELECT feito antes da primeira escrita
        # ficaria fora dela -- leitura suja dentro do proprio caso de uso.
        self.conexao.execute("BEGIN")
        return self

    def __exit__(self, tipo, valor, traceback) -> None:
        try:
            if tipo is None:
                self.conexao.commit()
            else:
                self.conexao.rollback()
        finally:
            self.conexao.close()
            self.conexao = None
            self._repositorios.clear()

    # -- acesso aos repositorios --------------------------------------------
    def repositorio(self, classe):
        """
        Devolve o repositorio pedido, ligado a ESTA transacao.

        Cacheado por unidade para que dois servicos no mesmo caso de uso vejam
        exatamente o mesmo estado nao commitado.
        """
        if classe not in self._repositorios:
            self._repositorios[classe] = classe(self.conexao)
        return self._repositorios[classe]
