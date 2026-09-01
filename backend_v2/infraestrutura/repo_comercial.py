"""Repositorios de cadastro, catalogo e estoque."""
from __future__ import annotations

from .base import Repositorio


class RepositorioParceiros(Repositorio):
    tabela = "parceiros"

    def buscar_ativo(self, identificador: int) -> dict | None:
        return self._um('SELECT * FROM parceiros WHERE id=? AND ativo=1', (identificador,))

    def por_documento(self, documento: str) -> dict | None:
        if not documento:
            return None
        return self._um(
            'SELECT * FROM parceiros WHERE documento=? AND ativo=1', (documento,)
        )

    def listar(self, *, busca='', papel='', cidade='', limite=50, deslocamento=0):
        condicoes = ['ativo = 1']
        parametros: list = []
        if busca:
            condicoes.append('(nome LIKE ? OR nome_fantasia LIKE ? OR documento LIKE ?)')
            curinga = '%%%s%%' % busca
            parametros += [curinga, curinga, curinga]
        if papel == 'cliente':
            condicoes.append('e_cliente = 1')
        elif papel == 'fornecedor':
            condicoes.append('e_fornecedor = 1')
        if cidade:
            condicoes.append('cidade LIKE ?')
            parametros.append('%%%s%%' % cidade)
        onde = ' AND '.join(condicoes)
        total = self._escalar('SELECT COUNT(*) FROM parceiros WHERE %s' % onde, parametros)
        itens = self._varios(
            'SELECT * FROM parceiros WHERE %s ORDER BY nome LIMIT ? OFFSET ?' % onde,
            parametros + [limite, deslocamento],
        )
        return itens, int(total or 0)

    def inserir(self, campos: dict) -> int:
        return self._inserir('parceiros', campos)

    def atualizar(self, identificador: int, campos: dict) -> int:
        return self._atualizar('parceiros', identificador, campos)

    def inativar(self, identificador: int) -> int:
        """
        Inativa em vez de apagar. Um parceiro com pedido ou titulo nao pode
        sumir: as FKs sao RESTRICT justamente para isso, e apagar deixaria
        historico orfao.
        """
        cursor = self.conexao.execute(
            "UPDATE parceiros SET ativo=0, "
            "inativado_em=datetime('now', 'localtime'), "
            "atualizado_em=datetime('now', 'localtime') "
            "WHERE id=? AND ativo=1",
            (identificador,),
        )
        return cursor.rowcount

    def tem_movimento(self, identificador: int) -> bool:
        """Ha documento ou titulo apontando para este parceiro?"""
        return bool(self._escalar(
            "SELECT EXISTS ("
            "  SELECT 1 FROM documentos_venda WHERE parceiro_id=? "
            "  UNION ALL SELECT 1 FROM documentos_compra WHERE parceiro_id=? "
            "  UNION ALL SELECT 1 FROM titulos WHERE parceiro_id=?"
            ")",
            (identificador, identificador, identificador),
        ))


class RepositorioProdutos(Repositorio):
    tabela = "produtos"

    def buscar_ativo(self, identificador: int) -> dict | None:
        return self._um('SELECT * FROM produtos WHERE id=? AND ativo=1', (identificador,))

    def por_codigo(self, codigo: str) -> dict | None:
        return self._um('SELECT * FROM produtos WHERE codigo=? AND ativo=1', (codigo,))

    def listar(self, *, busca='', apenas_estocaveis=False, limite=50, deslocamento=0):
        condicoes = ['ativo = 1']
        parametros: list = []
        if busca:
            condicoes.append('(codigo LIKE ? OR descricao LIKE ?)')
            curinga = '%%%s%%' % busca
            parametros += [curinga, curinga]
        if apenas_estocaveis:
            condicoes.append('controla_estoque = 1')
        onde = ' AND '.join(condicoes)
        total = self._escalar('SELECT COUNT(*) FROM produtos WHERE %s' % onde, parametros)
        itens = self._varios(
            'SELECT * FROM produtos WHERE %s ORDER BY descricao LIMIT ? OFFSET ?' % onde,
            parametros + [limite, deslocamento],
        )
        return itens, int(total or 0)

    def inserir(self, campos: dict) -> int:
        return self._inserir('produtos', campos)

    def atualizar(self, identificador: int, campos: dict) -> int:
        return self._atualizar('produtos', identificador, campos)

    def inativar(self, identificador: int) -> int:
        cursor = self.conexao.execute(
            "UPDATE produtos SET ativo=0, atualizado_em=datetime('now', 'localtime') "
            "WHERE id=? AND ativo=1",
            (identificador,),
        )
        return cursor.rowcount

    def atualizar_custo_medio(self, identificador: int, custo_centavos: int) -> None:
        self.conexao.execute(
            "UPDATE produtos SET custo_medio_centavos=?, "
            "atualizado_em=datetime('now', 'localtime') WHERE id=?",
            (int(custo_centavos), identificador),
        )


class RepositorioEstoque(Repositorio):
    tabela = "estoque_movimentos"

    def saldo(self, produto_id: int) -> int:
        """Saldo = soma da razao. Nunca um campo guardado que pode divergir."""
        return int(self._escalar(
            'SELECT COALESCE(SUM(quantidade), 0) FROM estoque_movimentos WHERE produto_id=?',
            (produto_id,),
        ) or 0)

    def saldos(self, *, apenas_abaixo_do_minimo=False, limite=50, deslocamento=0):
        onde = 'WHERE abaixo_do_minimo = 1' if apenas_abaixo_do_minimo else ''
        total = self._escalar('SELECT COUNT(*) FROM estoque_saldos %s' % onde)
        itens = self._varios(
            'SELECT * FROM estoque_saldos %s ORDER BY descricao LIMIT ? OFFSET ?' % onde,
            (limite, deslocamento),
        )
        return itens, int(total or 0)

    def movimentar(self, campos: dict) -> int:
        return self._inserir('estoque_movimentos', campos)

    def historico(self, produto_id: int, *, limite=50, deslocamento=0):
        total = self._escalar(
            'SELECT COUNT(*) FROM estoque_movimentos WHERE produto_id=?', (produto_id,)
        )
        itens = self._varios(
            'SELECT * FROM estoque_movimentos WHERE produto_id=? '
            'ORDER BY id DESC LIMIT ? OFFSET ?',
            (produto_id, limite, deslocamento),
        )
        return itens, int(total or 0)

    def movimentos_da_origem(self, origem_tipo: str, origem_id: int) -> list[dict]:
        return self._varios(
            'SELECT * FROM estoque_movimentos WHERE origem_tipo=? AND origem_id=? '
            'AND movimento_estornado_id IS NULL ORDER BY id',
            (origem_tipo, origem_id),
        )

    def ja_estornado(self, movimento_id: int) -> bool:
        return bool(self._escalar(
            'SELECT EXISTS (SELECT 1 FROM estoque_movimentos WHERE movimento_estornado_id=?)',
            (movimento_id,),
        ))
