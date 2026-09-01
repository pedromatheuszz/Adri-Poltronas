"""Repositorios de documentos de venda e compra, e a numeracao deles."""
from __future__ import annotations

from datetime import date

from .base import Repositorio


class RepositorioNumeracao(Repositorio):
    """
    Numero sequencial por especie e exercicio.

    O incremento acontece DENTRO da transacao do documento: se o documento for
    desfeito, o numero volta junto e nao abre buraco na sequencia. Usar
    `MAX(numero)+1` (o atalho comum) da numero repetido assim que dois
    lancamentos acontecem ao mesmo tempo.
    """

    def proximo(self, especie: str, exercicio: int | None = None) -> str:
        ano = exercicio or date.today().year
        self.conexao.execute(
            'INSERT INTO numeracao (especie, exercicio, ultimo) VALUES (?, ?, 0) '
            'ON CONFLICT(especie, exercicio) DO NOTHING',
            (especie, ano),
        )
        self.conexao.execute(
            'UPDATE numeracao SET ultimo = ultimo + 1 WHERE especie=? AND exercicio=?',
            (especie, ano),
        )
        sequencial = self._escalar(
            'SELECT ultimo FROM numeracao WHERE especie=? AND exercicio=?', (especie, ano)
        )
        return '%s-%d-%06d' % (especie[:3].upper(), ano, int(sequencial))


class _RepositorioDocumento(Repositorio):
    """Parte comum entre venda e compra: as duas sao cabecalho + itens."""

    tabela_itens = ""

    def com_itens(self, identificador: int) -> dict | None:
        documento = self.buscar(identificador)
        if not documento:
            return None
        documento['itens'] = self._varios(
            'SELECT * FROM %s WHERE documento_id=? ORDER BY sequencia, id' % self.tabela_itens,
            (identificador,),
        )
        return documento

    def inserir_item(self, campos: dict) -> int:
        return self._inserir(self.tabela_itens, campos)

    def remover_itens(self, documento_id: int) -> int:
        cursor = self.conexao.execute(
            'DELETE FROM %s WHERE documento_id=?' % self.tabela_itens, (documento_id,)
        )
        return cursor.rowcount

    def proxima_sequencia(self, documento_id: int) -> int:
        atual = self._escalar(
            'SELECT COALESCE(MAX(sequencia), 0) FROM %s WHERE documento_id=?' % self.tabela_itens,
            (documento_id,),
        )
        return int(atual or 0) + 1

    def somar_itens(self, documento_id: int) -> int:
        return int(self._escalar(
            'SELECT COALESCE(SUM(total_centavos), 0) FROM %s WHERE documento_id=?'
            % self.tabela_itens,
            (documento_id,),
        ) or 0)


class RepositorioVendas(_RepositorioDocumento):
    tabela = "documentos_venda"
    tabela_itens = "documentos_venda_itens"

    def listar(self, *, situacao='', especie='', parceiro_id=None,
               de='', ate='', limite=50, deslocamento=0):
        condicoes = ['1=1']
        parametros: list = []
        if situacao:
            condicoes.append('situacao = ?')
            parametros.append(situacao)
        if especie:
            condicoes.append('especie = ?')
            parametros.append(especie)
        if parceiro_id:
            condicoes.append('parceiro_id = ?')
            parametros.append(parceiro_id)
        if de:
            condicoes.append('data_emissao >= ?')
            parametros.append(de)
        if ate:
            condicoes.append('data_emissao <= ?')
            parametros.append(ate)
        onde = ' AND '.join(condicoes)
        total = self._escalar('SELECT COUNT(*) FROM documentos_venda WHERE %s' % onde, parametros)
        itens = self._varios(
            'SELECT d.*, p.nome AS parceiro_nome FROM documentos_venda d '
            'JOIN parceiros p ON p.id = d.parceiro_id '
            'WHERE %s ORDER BY d.id DESC LIMIT ? OFFSET ?' % onde,
            parametros + [limite, deslocamento],
        )
        return itens, int(total or 0)

    def inserir(self, campos: dict) -> int:
        return self._inserir('documentos_venda', campos)

    def atualizar(self, identificador: int, campos: dict) -> int:
        return self._atualizar('documentos_venda', identificador, campos)


class RepositorioCompras(_RepositorioDocumento):
    tabela = "documentos_compra"
    tabela_itens = "documentos_compra_itens"

    def listar(self, *, situacao='', parceiro_id=None, de='', ate='',
               limite=50, deslocamento=0):
        condicoes = ['1=1']
        parametros: list = []
        if situacao:
            condicoes.append('situacao = ?')
            parametros.append(situacao)
        if parceiro_id:
            condicoes.append('parceiro_id = ?')
            parametros.append(parceiro_id)
        if de:
            condicoes.append('data_emissao >= ?')
            parametros.append(de)
        if ate:
            condicoes.append('data_emissao <= ?')
            parametros.append(ate)
        onde = ' AND '.join(condicoes)
        total = self._escalar('SELECT COUNT(*) FROM documentos_compra WHERE %s' % onde, parametros)
        itens = self._varios(
            'SELECT d.*, p.nome AS parceiro_nome FROM documentos_compra d '
            'JOIN parceiros p ON p.id = d.parceiro_id '
            'WHERE %s ORDER BY d.id DESC LIMIT ? OFFSET ?' % onde,
            parametros + [limite, deslocamento],
        )
        return itens, int(total or 0)

    def inserir(self, campos: dict) -> int:
        return self._inserir('documentos_compra', campos)

    def atualizar(self, identificador: int, campos: dict) -> int:
        return self._atualizar('documentos_compra', identificador, campos)
