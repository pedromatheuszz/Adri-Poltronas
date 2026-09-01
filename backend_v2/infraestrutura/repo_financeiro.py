"""Repositorios de titulos, baixas, contas financeiras, caixa e entregas."""
from __future__ import annotations

from .base import Repositorio


class RepositorioTitulos(Repositorio):
    tabela = "titulos"

    def situacao(self, titulo_id: int) -> dict | None:
        """
        Le a view, nao a tabela: situacao e saldo sao DERIVADOS das baixas.

        Nenhum servico decide sozinho se um titulo esta quitado -- e sempre a
        mesma conta, no mesmo lugar.
        """
        return self._um('SELECT * FROM titulos_situacao WHERE titulo_id=?', (titulo_id,))

    def completo(self, titulo_id: int) -> dict | None:
        titulo = self.buscar(titulo_id)
        if not titulo:
            return None
        titulo.update(self.situacao(titulo_id) or {})
        titulo['baixas'] = self._varios(
            'SELECT * FROM titulo_baixas WHERE titulo_id=? ORDER BY id', (titulo_id,)
        )
        return titulo

    def listar(self, *, natureza='', situacao='', parceiro_id=None,
               vence_de='', vence_ate='', limite=50, deslocamento=0):
        condicoes = ['1=1']
        parametros: list = []
        if natureza:
            condicoes.append('s.natureza = ?')
            parametros.append(natureza)
        if situacao:
            condicoes.append('s.situacao = ?')
            parametros.append(situacao)
        if parceiro_id:
            condicoes.append('s.parceiro_id = ?')
            parametros.append(parceiro_id)
        if vence_de:
            condicoes.append('s.data_vencimento >= ?')
            parametros.append(vence_de)
        if vence_ate:
            condicoes.append('s.data_vencimento <= ?')
            parametros.append(vence_ate)
        onde = ' AND '.join(condicoes)
        total = self._escalar(
            'SELECT COUNT(*) FROM titulos_situacao s WHERE %s' % onde, parametros
        )
        itens = self._varios(
            'SELECT s.*, t.descricao, t.parcela, t.total_parcelas, t.data_emissao, '
            '       t.forma_pagamento, t.origem_tipo, t.origem_id, p.nome AS parceiro_nome '
            '  FROM titulos_situacao s '
            '  JOIN titulos t ON t.id = s.titulo_id '
            '  JOIN parceiros p ON p.id = s.parceiro_id '
            ' WHERE %s ORDER BY s.data_vencimento, s.titulo_id LIMIT ? OFFSET ?' % onde,
            parametros + [limite, deslocamento],
        )
        return itens, int(total or 0)

    def inserir(self, campos: dict) -> int:
        return self._inserir('titulos', campos)

    def cancelar(self, titulo_id: int, motivo: str) -> int:
        cursor = self.conexao.execute(
            "UPDATE titulos SET cancelado=1, "
            "cancelado_em=datetime('now', 'localtime'), motivo_cancelamento=? "
            "WHERE id=? AND cancelado=0",
            (motivo, titulo_id),
        )
        return cursor.rowcount

    def da_origem(self, origem_tipo: str, origem_id: int) -> list[dict]:
        return self._varios(
            'SELECT * FROM titulos WHERE origem_tipo=? AND origem_id=? ORDER BY parcela',
            (origem_tipo, origem_id),
        )

    # -- agregados para o painel --------------------------------------------
    def totais_por_situacao(self, natureza: str) -> dict:
        linhas = self._varios(
            'SELECT situacao, COUNT(*) AS quantidade, '
            '       COALESCE(SUM(saldo_centavos), 0) AS saldo_centavos '
            '  FROM titulos_situacao WHERE natureza=? AND cancelado=0 '
            ' GROUP BY situacao',
            (natureza,),
        )
        return {linha['situacao']: linha for linha in linhas}


class RepositorioBaixas(Repositorio):
    tabela = "titulo_baixas"

    def inserir(self, campos: dict) -> int:
        return self._inserir('titulo_baixas', campos)

    def estornar(self, baixa_id: int) -> int:
        cursor = self.conexao.execute(
            "UPDATE titulo_baixas SET estornada=1, "
            "estornada_em=datetime('now', 'localtime') WHERE id=? AND estornada=0",
            (baixa_id,),
        )
        return cursor.rowcount

    def por_periodo(self, de: str, ate: str) -> list[dict]:
        return self._varios(
            'SELECT b.*, t.natureza, t.parceiro_id FROM titulo_baixas b '
            'JOIN titulos t ON t.id = b.titulo_id '
            'WHERE b.estornada = 0 AND b.data_baixa BETWEEN ? AND ? '
            'ORDER BY b.data_baixa, b.id',
            (de, ate),
        )


class RepositorioContas(Repositorio):
    tabela = "contas_financeiras"

    def buscar_ativa(self, identificador: int) -> dict | None:
        return self._um(
            'SELECT * FROM contas_financeiras WHERE id=? AND ativo=1', (identificador,)
        )

    def listar_com_saldo(self) -> list[dict]:
        return self._varios('SELECT * FROM contas_saldos ORDER BY nome')

    def saldo(self, conta_id: int) -> int:
        return int(self._escalar(
            'SELECT saldo_centavos FROM contas_saldos WHERE conta_id=?', (conta_id,)
        ) or 0)

    def inserir(self, campos: dict) -> int:
        return self._inserir('contas_financeiras', campos)


class RepositorioCaixa(Repositorio):
    tabela = "movimentos_caixa"

    def lancar(self, campos: dict) -> int:
        return self._inserir('movimentos_caixa', campos)

    def extrato(self, *, conta_id=None, de='', ate='', limite=50, deslocamento=0):
        condicoes = ['1=1']
        parametros: list = []
        if conta_id:
            condicoes.append('m.conta_id = ?')
            parametros.append(conta_id)
        if de:
            condicoes.append('m.data_movimento >= ?')
            parametros.append(de)
        if ate:
            condicoes.append('m.data_movimento <= ?')
            parametros.append(ate)
        onde = ' AND '.join(condicoes)
        total = self._escalar('SELECT COUNT(*) FROM movimentos_caixa m WHERE %s' % onde, parametros)
        itens = self._varios(
            'SELECT m.*, c.nome AS conta_nome FROM movimentos_caixa m '
            'JOIN contas_financeiras c ON c.id = m.conta_id '
            'WHERE %s ORDER BY m.data_movimento DESC, m.id DESC LIMIT ? OFFSET ?' % onde,
            parametros + [limite, deslocamento],
        )
        return itens, int(total or 0)

    def fluxo_por_dia(self, de: str, ate: str) -> list[dict]:
        return self._varios(
            "SELECT data_movimento AS dia, "
            "       COALESCE(SUM(CASE WHEN valor_centavos > 0 THEN valor_centavos END), 0) AS entradas, "
            "       COALESCE(SUM(CASE WHEN valor_centavos < 0 THEN -valor_centavos END), 0) AS saidas, "
            "       COALESCE(SUM(valor_centavos), 0) AS liquido "
            "  FROM movimentos_caixa WHERE data_movimento BETWEEN ? AND ? "
            " GROUP BY data_movimento ORDER BY data_movimento",
            (de, ate),
        )


class RepositorioEntregas(Repositorio):
    tabela = "entregas"

    def listar(self, *, situacao='', de='', ate='', limite=50, deslocamento=0):
        condicoes = ['1=1']
        parametros: list = []
        if situacao:
            condicoes.append('e.situacao = ?')
            parametros.append(situacao)
        if de:
            condicoes.append('e.data_prevista >= ?')
            parametros.append(de)
        if ate:
            condicoes.append('e.data_prevista <= ?')
            parametros.append(ate)
        onde = ' AND '.join(condicoes)
        total = self._escalar('SELECT COUNT(*) FROM entregas e WHERE %s' % onde, parametros)
        itens = self._varios(
            'SELECT e.*, p.nome AS parceiro_nome FROM entregas e '
            'JOIN parceiros p ON p.id = e.parceiro_id '
            'WHERE %s ORDER BY e.data_prevista, e.hora_prevista LIMIT ? OFFSET ?' % onde,
            parametros + [limite, deslocamento],
        )
        return itens, int(total or 0)

    def inserir(self, campos: dict) -> int:
        return self._inserir('entregas', campos)

    def atualizar(self, identificador: int, campos: dict) -> int:
        return self._atualizar('entregas', identificador, campos)
