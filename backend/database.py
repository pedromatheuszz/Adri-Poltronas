import sqlite3
import os
import logging
from datetime import datetime

import security
import asaas



def obter_caminho_banco() -> str:
    override = os.environ.get("ADRI_DB_PATH")
    if override:
        return override
    appdata = os.environ.get("APPDATA")
    if appdata:
        pasta_dados = os.path.join(appdata, "AdriPoltronas")
        try:
            os.makedirs(pasta_dados, exist_ok=True)
        except OSError:
            pass
        else:
            return os.path.join(pasta_dados, "adri_poltronas.db")
    return os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "..",
        "adri_poltronas.db",
    )


DB_PATH = obter_caminho_banco()
_log_db = logging.getLogger("adri.db")


def conectar_bd() -> sqlite3.Connection:
    conexao = sqlite3.connect(DB_PATH, timeout=10)
    conexao.row_factory = sqlite3.Row
    return conexao


class _ConexaoCM:
    def __enter__(self) -> sqlite3.Connection:
        self._conexao = conectar_bd()
        return self._conexao

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        try:
            if exc_type is None:
                self._conexao.commit()
        finally:
            self._conexao.close()


def conectar():
    return _ConexaoCM()


def criar_tabela():
    with conectar() as conexao:
        cursor = conexao.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS clientes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL,
                cep TEXT,
                rua TEXT,
                bairro TEXT,
                cidade TEXT,
                entrega_retirada TEXT NOT NULL DEFAULT 'Entrega',
                observacoes TEXT DEFAULT '',
                criado_em TEXT DEFAULT (datetime('now', 'localtime')),
                atualizado_em TEXT DEFAULT (datetime('now', 'localtime'))
            )
        ''')
        for coluna, tipo_default in [
            ("entrega_retirada", "TEXT NOT NULL DEFAULT 'Entrega'"),
            ("observacoes", "TEXT DEFAULT ''"),
            ("criado_em", "TEXT"),
            ("atualizado_em", "TEXT"),
        ]:
            try:
                cursor.execute(f"ALTER TABLE clientes ADD COLUMN {coluna} {tipo_default}")
                if coluna in ('criado_em', 'atualizado_em'):
                    cursor.execute(f"UPDATE clientes SET {coluna} = datetime('now', 'localtime') WHERE {coluna} IS NULL")
            except Exception:
                pass

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sessao (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                token TEXT NOT NULL,
                conta TEXT NOT NULL
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS historico (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cliente_id INTEGER,
                cliente_nome TEXT,
                acao TEXT NOT NULL,
                detalhes TEXT DEFAULT '',
                data_hora TEXT DEFAULT (datetime('now', 'localtime'))
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS pagamentos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cliente_id INTEGER NOT NULL,
                cliente_nome TEXT DEFAULT '',
                valor REAL NOT NULL DEFAULT 0,
                descricao TEXT DEFAULT '',
                status TEXT NOT NULL DEFAULT 'Pendente',
                data_pagamento TEXT DEFAULT '',
                data_vencimento TEXT DEFAULT '',
                criado_em TEXT DEFAULT (datetime('now', 'localtime')),
                tipo_pagamento TEXT NOT NULL DEFAULT 'Pix',
                asaas_payment_id TEXT DEFAULT '',
                pix_payload TEXT DEFAULT '',
                pix_qr_code TEXT DEFAULT '',
                boleto_url TEXT DEFAULT '',
                nosso_numero TEXT DEFAULT ''
            )
        ''')
        for coluna, tipo_default in [
            ("data_vencimento", "TEXT DEFAULT ''"),
            ("tipo_pagamento", "TEXT NOT NULL DEFAULT 'Pix'"),
            ("asaas_payment_id", "TEXT DEFAULT ''"),
            ("pix_payload", "TEXT DEFAULT ''"),
            ("pix_qr_code", "TEXT DEFAULT ''"),
            ("boleto_url", "TEXT DEFAULT ''"),
            ("nosso_numero", "TEXT DEFAULT ''"),
        ]:
            try:
                cursor.execute(f"ALTER TABLE pagamentos ADD COLUMN {coluna} {tipo_default}")
            except Exception:
                pass

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS clientes_asaas (
                cliente_id INTEGER PRIMARY KEY,
                asaas_customer_id TEXT NOT NULL DEFAULT ''
            )
        ''')

        # As notificacoes sao derivadas de consultas, nao armazenadas. O estado
        # de "lida" precisa entao de uma chave estavel por notificacao
        # (tipo:id_da_entidade), guardada aqui.
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS notificacoes_lidas (
                chave TEXT PRIMARY KEY,
                lida_em TEXT DEFAULT (datetime('now', 'localtime'))
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS entregas_agendadas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cliente_id INTEGER NOT NULL,
                cliente_nome TEXT DEFAULT '',
                data_entrega TEXT NOT NULL,
                hora_entrega TEXT DEFAULT '',
                descricao TEXT DEFAULT '',
                status TEXT NOT NULL DEFAULT 'Pendente',
                criado_em TEXT DEFAULT (datetime('now', 'localtime'))
            )
        ''')


def salvar_cliente(nome, cep, rua, bairro, cidade, entrega_retirada, observacoes=''):
    with conectar() as conexao:
        conexao.execute(
            'INSERT INTO clientes (nome, cep, rua, bairro, cidade, entrega_retirada, observacoes) VALUES (?, ?, ?, ?, ?, ?, ?)',
            (nome, cep, rua, bairro, cidade, entrega_retirada, observacoes),
        )
        cliente_id = conexao.execute('SELECT last_insert_rowid()').fetchone()[0]
        conexao.execute(
            'INSERT INTO historico (cliente_id, cliente_nome, acao, detalhes) VALUES (?, ?, ?, ?)',
            (cliente_id, nome, 'CRIACAO', 'Cliente cadastrado'),
        )
        return cliente_id


def listar_clientes(busca=''):
    termo = (busca or '').strip()
    with conectar() as conexao:
        if termo:
            like = f'%{termo}%'
            linhas = conexao.execute(
                'SELECT * FROM clientes WHERE nome LIKE ? OR cidade LIKE ? OR bairro LIKE ? ORDER BY id DESC',
                (like, like, like),
            ).fetchall()
        else:
            linhas = conexao.execute('SELECT * FROM clientes ORDER BY id DESC').fetchall()
    resultado = []
    for linha in linhas:
        try:
            obs = linha["observacoes"] or ""
        except (IndexError, KeyError):
            obs = ""
        try:
            criado = linha["criado_em"] or ""
        except (IndexError, KeyError):
            criado = ""
        try:
            atualizado = linha["atualizado_em"] or ""
        except (IndexError, KeyError):
            atualizado = ""
        resultado.append({
            "id": linha["id"],
            "nome": linha["nome"],
            "cep": linha["cep"],
            "rua": linha["rua"],
            "bairro": linha["bairro"],
            "cidade": linha["cidade"],
            "entrega_retirada": linha["entrega_retirada"],
            "observacoes": obs,
            "criado_em": criado,
            "atualizado_em": atualizado,
        })
    return resultado


def obter_cliente_por_id(id_cliente):
    with conectar() as conexao:
        linha = conexao.execute('SELECT * FROM clientes WHERE id=?', (id_cliente,)).fetchone()
        if not linha:
            return None
        return dict(linha)


def atualizar_cliente(id_cliente, nome, cep, rua, bairro, cidade, entrega_retirada, observacoes=''):
    with conectar() as conexao:
        antigo = conexao.execute('SELECT * FROM clientes WHERE id=?', (id_cliente,)).fetchone()
        conexao.execute(
            'UPDATE clientes SET nome=?, cep=?, rua=?, bairro=?, cidade=?, entrega_retirada=?, observacoes=?, atualizado_em=datetime(\'now\', \'localtime\') WHERE id=?',
            (nome, cep, rua, bairro, cidade, entrega_retirada, observacoes, id_cliente),
        )
        detalhes_parts = []
        if antigo:
            novos_vals = {
                'nome': nome, 'cep': cep, 'rua': rua,
                'bairro': bairro, 'cidade': cidade,
                'entrega_retirada': entrega_retirada, 'observacoes': observacoes,
            }
            for campo, label in [('nome', 'Nome'), ('cep', 'CEP'), ('rua', 'Rua'),
                                  ('bairro', 'Bairro'), ('cidade', 'Cidade'),
                                  ('entrega_retirada', 'Tipo'), ('observacoes', 'Obs')]:
                val_novo = novos_vals[campo]
                val_antigo = antigo[campo] or ''
                if str(val_novo) != str(val_antigo):
                    detalhes_parts.append(f"{label}: '{val_antigo}' -> '{val_novo}'")
        detalhes = '; '.join(detalhes_parts) if detalhes_parts else 'Atualização sem alterações detectadas'
        conexao.execute(
            'INSERT INTO historico (cliente_id, cliente_nome, acao, detalhes) VALUES (?, ?, ?, ?)',
            (id_cliente, nome, 'ATUALIZACAO', detalhes),
        )


def excluir_cliente(id_cliente) -> int:
    with conectar() as conexao:
        antigo = conexao.execute('SELECT * FROM clientes WHERE id=?', (id_cliente,)).fetchone()
        cursor = conexao.execute('DELETE FROM clientes WHERE id=?', (id_cliente,))
        if antigo and cursor.rowcount > 0:
            conexao.execute(
                'INSERT INTO historico (cliente_id, cliente_nome, acao, detalhes) VALUES (?, ?, ?, ?)',
                (id_cliente, antigo['nome'], 'EXCLUSAO', f"Cliente excluído: {antigo['nome']}, {antigo['cidade'] or ''}, {antigo['bairro'] or ''}"),
            )
        return cursor.rowcount


def importar_clientes_em_lote(clientes_lista):
    sucessos = 0
    duplicados = 0
    erros = 0
    with conectar() as conexao:
        for c in clientes_lista:
            nome = (c.get('nome') or '').strip()
            cep = (c.get('cep') or '').strip()
            if not nome or not cep:
                erros += 1
                continue
            existente = conexao.execute('SELECT id FROM clientes WHERE nome=? AND cep=?', (nome, cep)).fetchone()
            if existente:
                duplicados += 1
                continue
            conexao.execute(
                'INSERT INTO clientes (nome, cep, rua, bairro, cidade, entrega_retirada, observacoes) VALUES (?, ?, ?, ?, ?, ?, ?)',
                (nome, cep, (c.get('rua') or '').strip(), (c.get('bairro') or '').strip(), (c.get('cidade') or '').strip(), (c.get('entrega_retirada') or 'Entrega').strip(), (c.get('observacoes') or '').strip()),
            )
            cliente_id = conexao.execute('SELECT last_insert_rowid()').fetchone()[0]
            conexao.execute(
                'INSERT INTO historico (cliente_id, cliente_nome, acao, detalhes) VALUES (?, ?, ?, ?)',
                (cliente_id, nome, 'IMPORTACAO', 'Importado em lote'),
            )
            sucessos += 1
    return {"sucessos": sucessos, "duplicados": duplicados, "erros": erros}


def excluir_sessao():
    with conectar() as conexao:
        conexao.execute('DELETE FROM sessao')


def salvar_sessao(token, conta):
    with conectar() as conexao:
        conexao.execute('DELETE FROM sessao')
        token_cifrado = security.cifrar(token)
        conexao.execute('INSERT INTO sessao (token, conta) VALUES (?, ?)', (token_cifrado, conta))


def obter_sessao():
    with conectar() as conexao:
        linha = conexao.execute('SELECT token, conta FROM sessao LIMIT 1').fetchone()
        if linha:
            token_decifrado = security.decifrar(linha['token'])
            if token_decifrado is None:
                return None
            return {"token": token_decifrado, "conta": linha["conta"]}
    return None


def obter_caminho_banco_absoluto() -> str:
    return os.path.abspath(DB_PATH)


def listar_pagamentos(cliente_id=None, status=None):
    with conectar() as conexao:
        query = 'SELECT * FROM pagamentos WHERE 1=1'
        params = []
        if cliente_id:
            query += ' AND cliente_id=?'
            params.append(cliente_id)
        if status:
            query += ' AND status=?'
            params.append(status)
        query += ' ORDER BY id DESC'
        linhas = conexao.execute(query, params).fetchall()
    return [dict(linha) for linha in linhas]


def salvar_pagamento(cliente_id, cliente_nome, valor, descricao, data_vencimento, tipo_pagamento='Pix'):
    """Cria um novo pagamento e retorna o ID."""
    with conectar() as conexao:
        conexao.execute(
            'INSERT INTO pagamentos (cliente_id, cliente_nome, valor, descricao, status, data_vencimento, tipo_pagamento) '
            'VALUES (?, ?, ?, ?, ?, ?, ?)',
            (cliente_id, cliente_nome, valor, descricao, 'Pendente', data_vencimento, tipo_pagamento),
        )
        pagamento_id = conexao.execute('SELECT last_insert_rowid()').fetchone()[0]
        conexao.execute(
            'INSERT INTO historico (cliente_id, cliente_nome, acao, detalhes) VALUES (?, ?, ?, ?)',
            (cliente_id, cliente_nome, 'PAGAMENTO', f'Cobranca criada: R$ {valor:.2f} ({tipo_pagamento})'),
        )
        return pagamento_id


def atualizar_pagamento(pagamento_id, **kwargs):
    """Atualiza campos de um pagamento existente."""
    campos_permitidos = {
        'status', 'data_pagamento', 'asaas_payment_id', 'pix_payload',
        'pix_qr_code', 'boleto_url', 'nosso_numero', 'descricao',
        'valor', 'data_vencimento', 'tipo_pagamento', 'cliente_nome',
    }
    campos = {k: v for k, v in kwargs.items() if k in campos_permitidos and v is not None}
    if not campos:
        return 0
    sets = ', '.join(f'{k}=?' for k in campos)
    vals = list(campos.values()) + [pagamento_id]
    with conectar() as conexao:
        conexao.execute(f'UPDATE pagamentos SET {sets} WHERE id=?', vals)
        linhas = conexao.execute('SELECT changes()').fetchone()[0]
        if 'status' in campos and campos['status'] == 'Recebido':
            pagamento = conexao.execute('SELECT * FROM pagamentos WHERE id=?', (pagamento_id,)).fetchone()
            if pagamento:
                conexao.execute(
                    'INSERT INTO historico (cliente_id, cliente_nome, acao, detalhes) VALUES (?, ?, ?, ?)',
                    (pagamento['cliente_id'], pagamento['cliente_nome'], 'PAGAMENTO',
                     f'Pagamento confirmado: R$ {pagamento["valor"]:.2f}'),
                )
        return linhas


def excluir_pagamento(pagamento_id) -> int:
    """Exclui um pagamento pendente."""
    with conectar() as conexao:
        pagamento = conexao.execute('SELECT * FROM pagamentos WHERE id=?', (pagamento_id,)).fetchone()
        cursor = conexao.execute('DELETE FROM pagamentos WHERE id=? AND status="Pendente"', (pagamento_id,))
        if pagamento and cursor.rowcount > 0:
            conexao.execute(
                'INSERT INTO historico (cliente_id, cliente_nome, acao, detalhes) VALUES (?, ?, ?, ?)',
                (pagamento['cliente_id'], pagamento['cliente_nome'], 'PAGAMENTO',
                 f'Cobranca cancelada: R$ {pagamento["valor"]:.2f}'),
            )
        return cursor.rowcount


def obter_pagamento_por_id(pagamento_id):
    """Retorna um pagamento pelo ID."""
    with conectar() as conexao:
        linha = conexao.execute('SELECT * FROM pagamentos WHERE id=?', (pagamento_id,)).fetchone()
        return dict(linha) if linha else None


def obter_ou_criar_cliente_asaas(cliente_id, nome, cpf_cnpj=None, email=None, cidade=None, uf=None, bairro=None, rua=None, cep=None):
    """Retorna o asaas_customer_id existente ou cria um novo."""
    with conectar() as conexao:
        linha = conexao.execute('SELECT asaas_customer_id FROM clientes_asaas WHERE cliente_id=?', (cliente_id,)).fetchone()
        if linha and linha['asaas_customer_id']:
            return linha['asaas_customer_id']
        resultado = asaas.criar_cliente(nome, cpf_cnpj, email=email, cidade=cidade, uf=uf, bairro=bairro, rua=rua, cep=cep)
        if resultado.get('_erro'):
            return None
        asaas_id = resultado.get('id', '')
        if asaas_id:
            conexao.execute(
                'INSERT OR REPLACE INTO clientes_asaas (cliente_id, asaas_customer_id) VALUES (?, ?)',
                (cliente_id, asaas_id),
            )
        return asaas_id


def obter_metricas_pagamentos():
    """Retorna metricas de pagamentos para o dashboard."""
    with conectar() as conexao:
        total_recebido = conexao.execute(
            "SELECT COALESCE(SUM(valor), 0) FROM pagamentos WHERE status='Recebido'"
        ).fetchone()[0]
        total_pendente = conexao.execute(
            "SELECT COALESCE(SUM(valor), 0) FROM pagamentos WHERE status='Pendente'"
        ).fetchone()[0]
        total_atrasado = conexao.execute(
            "SELECT COALESCE(SUM(valor), 0) FROM pagamentos WHERE status='Pendente' AND data_vencimento < date('now', 'localtime')"
        ).fetchone()[0]
        qtd_recebido = conexao.execute(
            "SELECT COUNT(*) FROM pagamentos WHERE status='Recebido'"
        ).fetchone()[0]
        qtd_pendente = conexao.execute(
            "SELECT COUNT(*) FROM pagamentos WHERE status='Pendente'"
        ).fetchone()[0]
    return {
        'total_recebido': total_recebido or 0,
        'total_pendente': total_pendente or 0,
        'total_atrasado': total_atrasado or 0,
        'qtd_recebido': qtd_recebido or 0,
        'qtd_pendente': qtd_pendente or 0,
    }



# A data efetiva de um recebimento e a de pagamento; quando ela nao foi
# preenchida, cai para a criacao da cobranca. `date()` normaliza os dois
# formatos que convivem na coluna: 'AAAA-MM-DD' (confirmacao manual) e
# 'AAAA-MM-DD HH:MM:SS' (webhook do Asaas).
_DATA_RECEBIMENTO = "date(COALESCE(NULLIF(data_pagamento, ''), criado_em))"


def obter_metricas_financeiras(meses_historico=6):
    """
    Indicadores financeiros do dashboard: faturamento do mes corrente
    comparado ao anterior, valores a receber e em atraso, ticket medio e a
    serie mensal de receita.
    """
    with conectar() as conexao:
        def receita_do_mes(deslocamento):
            """Soma recebida no mes com `deslocamento` meses a partir do atual."""
            return conexao.execute(
                f"SELECT COALESCE(SUM(valor), 0) FROM pagamentos "
                f"WHERE status = 'Recebido' AND strftime('%Y-%m', {_DATA_RECEBIMENTO}) = "
                f"strftime('%Y-%m', date('now', 'localtime', ?))",
                (f'{deslocamento} months',),
            ).fetchone()[0] or 0

        faturamento_mes = receita_do_mes(0)
        faturamento_anterior = receita_do_mes(-1)

        qtd_mes = conexao.execute(
            f"SELECT COUNT(*) FROM pagamentos WHERE status = 'Recebido' "
            f"AND strftime('%Y-%m', {_DATA_RECEBIMENTO}) = strftime('%Y-%m', date('now', 'localtime'))"
        ).fetchone()[0] or 0

        a_receber = conexao.execute(
            "SELECT COALESCE(SUM(valor), 0) FROM pagamentos WHERE status = 'Pendente'"
        ).fetchone()[0] or 0

        em_atraso = conexao.execute(
            "SELECT COALESCE(SUM(valor), 0) FROM pagamentos "
            "WHERE status IN ('Pendente', 'Atrasado') "
            "AND data_vencimento != '' AND date(data_vencimento) < date('now', 'localtime')"
        ).fetchone()[0] or 0

        qtd_atraso = conexao.execute(
            "SELECT COUNT(*) FROM pagamentos "
            "WHERE status IN ('Pendente', 'Atrasado') "
            "AND data_vencimento != '' AND date(data_vencimento) < date('now', 'localtime')"
        ).fetchone()[0] or 0

        # Serie mensal: consulta uma vez e preenche os meses sem receita com
        # zero, para o grafico nao pular periodos.
        linhas = conexao.execute(
            f"SELECT strftime('%Y-%m', {_DATA_RECEBIMENTO}) AS mes, SUM(valor) AS total "
            f"FROM pagamentos WHERE status = 'Recebido' "
            f"AND {_DATA_RECEBIMENTO} >= date('now', 'localtime', ?) "
            f"GROUP BY mes",
            (f'-{meses_historico - 1} months',),
        ).fetchall()
        por_mes = {linha['mes']: linha['total'] or 0 for linha in linhas}

        meses = conexao.execute(
            "WITH RECURSIVE seq(n) AS (SELECT 0 UNION ALL SELECT n + 1 FROM seq WHERE n < ?) "
            "SELECT strftime('%Y-%m', date('now', 'localtime', '-' || (? - n) || ' months')) AS mes FROM seq",
            (meses_historico - 1, meses_historico - 1),
        ).fetchall()
        serie = [{'mes': m['mes'], 'total': round(por_mes.get(m['mes'], 0), 2)} for m in meses]

    variacao = None
    if faturamento_anterior:
        variacao = round(((faturamento_mes - faturamento_anterior) / faturamento_anterior) * 100, 1)
    elif faturamento_mes:
        variacao = 100.0

    return {
        'faturamento_mes': round(faturamento_mes, 2),
        'faturamento_mes_anterior': round(faturamento_anterior, 2),
        'variacao_percentual': variacao,
        'qtd_recebimentos_mes': qtd_mes,
        'ticket_medio_mes': round(faturamento_mes / qtd_mes, 2) if qtd_mes else 0,
        'a_receber': round(a_receber, 2),
        'em_atraso': round(em_atraso, 2),
        'qtd_em_atraso': qtd_atraso,
        'serie_mensal': serie,
    }


def obter_dados_grafico_por_tipo():
    """Retorna contagem de clientes por tipo (Entrega/Retirada) para gráfico de pizza."""
    with conectar() as conexao:
        linhas = conexao.execute(
            "SELECT entrega_retirada, COUNT(*) as total FROM clientes GROUP BY entrega_retirada"
        ).fetchall()
        return {row['entrega_retirada']: row['total'] for row in linhas}


def obter_dados_grafico_cidades(limite=10):
    """Retorna top N cidades com mais clientes para gráfico de barras."""
    with conectar() as conexao:
        linhas = conexao.execute(
            "SELECT cidade, COUNT(*) as total FROM clientes WHERE cidade IS NOT NULL AND cidade != '' GROUP BY cidade ORDER BY total DESC LIMIT ?",
            (limite,)
        ).fetchall()
        return [(row['cidade'], row['total']) for row in linhas]


def obter_dados_grafico_timeline(dias=30):
    """Retorna cadastros por dia nos últimos N dias para gráfico de linha."""
    with conectar() as conexao:
        linhas = conexao.execute(
            "SELECT date(criado_em) as dia, COUNT(*) as total FROM clientes WHERE criado_em >= date('now', '-' || ? || ' days', 'localtime') GROUP BY dia ORDER BY dia",
            (dias,)
        ).fetchall()
        return [(row['dia'], row['total']) for row in linhas]


def obter_clientes_para_mapa():
    """Retorna clientes individuais com CEP para geolocalizacao no mapa."""
    with conectar() as conexao:
        linhas = conexao.execute(
            "SELECT id, nome, cep, rua, bairro, cidade, entrega_retirada FROM clientes WHERE cep IS NOT NULL AND cep != '' ORDER BY id DESC"
        ).fetchall()
        return [{
            "id": row["id"],
            "nome": row["nome"],
            "cep": row["cep"],
            "rua": row["rua"] or '',
            "bairro": row["bairro"] or '',
            "cidade": row["cidade"] or '',
            "tipo": row["entrega_retirada"]
        } for row in linhas]


def listar_clientes_filtrados(tipo='', cidade='', data_inicio='', data_fim=''):
    """Retorna clientes filtrados por tipo, cidade e período para relatórios."""
    query = 'SELECT * FROM clientes WHERE 1=1'
    params = []
    if tipo:
        query += ' AND entrega_retirada=?'
        params.append(tipo)
    if cidade:
        query += ' AND cidade LIKE ?'
        params.append(f'%{cidade}%')
    if data_inicio:
        query += ' AND criado_em >= ?'
        params.append(data_inicio)
    if data_fim:
        query += ' AND criado_em <= ?'
        params.append(data_fim + ' 23:59:59')
    query += ' ORDER BY id DESC'
    with conectar() as conexao:
        linhas = conexao.execute(query, params).fetchall()
    return [{
        "id": row["id"], "nome": row["nome"], "cep": row["cep"],
        "rua": row["rua"] or '', "bairro": row["bairro"] or '',
        "cidade": row["cidade"] or '', "entrega_retirada": row["entrega_retirada"],
        "observacoes": row["observacoes"] or '',
        "criado_em": row["criado_em"] or '', "atualizado_em": row["atualizado_em"] or '',
    } for row in linhas]


def obter_perfis_regiao():
    """Retorna contagem de clientes por cidade para relatório de performance."""
    with conectar() as conexao:
        linhas = conexao.execute(
            "SELECT cidade, COUNT(*) as total, "
            "SUM(CASE WHEN entrega_retirada='Entrega' THEN 1 ELSE 0 END) as entregas, "
            "SUM(CASE WHEN entrega_retirada='Retirada' THEN 1 ELSE 0 END) as retiradas "
            "FROM clientes WHERE cidade IS NOT NULL AND cidade != '' GROUP BY cidade ORDER BY total DESC"
        ).fetchall()
    return [{
        "cidade": row["cidade"], "total": row["total"],
        "entregas": row["entregas"], "retiradas": row["retiradas"]
    } for row in linhas]


def obter_ultimos_clientes(limite=5):
    """Retorna os últimos N clientes cadastrados."""
    with conectar() as conexao:
        linhas = conexao.execute(
            'SELECT id, nome, cidade, bairro, entrega_retirada, criado_em FROM clientes ORDER BY id DESC LIMIT ?',
            (limite,)
        ).fetchall()
        return [{
            "id": row["id"], "nome": row["nome"], "cidade": row["cidade"],
            "bairro": row["bairro"], "tipo": row["entrega_retirada"],
            "data": row["criado_em"]
        } for row in linhas]


def obter_metricas_dashboard():
    try:
        with conectar() as conexao:
            total_clientes = conexao.execute('SELECT COUNT(*) FROM clientes').fetchone()[0] or 0
            total_entrega = conexao.execute("SELECT COUNT(*) FROM clientes WHERE entrega_retirada='Entrega'").fetchone()[0] or 0
            total_retirada = conexao.execute("SELECT COUNT(*) FROM clientes WHERE entrega_retirada='Retirada'").fetchone()[0] or 0
            try:
                cadastros_30d = conexao.execute("SELECT COUNT(*) FROM clientes WHERE criado_em >= datetime('now', '-30 days', 'localtime')").fetchone()[0] or 0
            except Exception:
                cadastros_30d = 0
            return {
                "total_clientes": total_clientes,
                "total_entrega": total_entrega,
                "total_retirada": total_retirada,
                "cadastros_30d": cadastros_30d,
            }
    except Exception:
        _log_db.exception("Erro ao obter metricas do dashboard")
        return {"total_clientes": 0, "total_entrega": 0, "total_retirada": 0, "cadastros_30d": 0}


# -----------------------------------------------------------------------------
# Entregas Agendadas
# -----------------------------------------------------------------------------
def agendar_entrega(cliente_id, cliente_nome, data_entrega, hora_entrega='', descricao=''):
    with conectar() as conexao:
        conexao.execute(
            'INSERT INTO entregas_agendadas (cliente_id, cliente_nome, data_entrega, hora_entrega, descricao) VALUES (?, ?, ?, ?, ?)',
            (cliente_id, cliente_nome, data_entrega, hora_entrega, descricao),
        )
        return conexao.execute('SELECT last_insert_rowid()').fetchone()[0]


def listar_entregas_agendadas(status=None):
    with conectar() as conexao:
        query = 'SELECT * FROM entregas_agendadas'
        params = []
        if status:
            query += ' WHERE status=?'
            params.append(status)
        query += ' ORDER BY data_entrega ASC'
        linhas = conexao.execute(query, params).fetchall()
        return [dict(linha) for linha in linhas]


def atualizar_status_entrega(entrega_id, novo_status):
    with conectar() as conexao:
        conexao.execute('UPDATE entregas_agendadas SET status=? WHERE id=?', (novo_status, entrega_id))
        return conexao.execute('SELECT changes()').fetchone()[0]


def obter_notificacoes():
    """Gera lista inteligente de notificacoes do sistema."""
    notifs = []
    with conectar() as conexao:
        # 1. Entregas agendadas para hoje
        entregas_hoje = conexao.execute(
            "SELECT * FROM entregas_agendadas WHERE date(data_entrega) = date('now', 'localtime') AND status != 'Concluida'"
        ).fetchall()
        for e in entregas_hoje:
            notifs.append({
                'tipo': 'entrega_hoje',
                'chave': f"entrega_hoje:{e['id']}",
                'prioridade': 'alta',
                'icone': '📦',
                'msg': f"Entrega agendada para HOJE: {e['cliente_nome']}" + (f" as {e['hora_entrega']}" if e['hora_entrega'] else ''),
                'detalhes': e['descricao'] or '',
                'entrega_id': e['id'],
                'data': e['data_entrega']
            })

        # 2. Entregas proximas (3 dias)
        entregas_proximas = conexao.execute(
            "SELECT * FROM entregas_agendadas WHERE date(data_entrega) > date('now', 'localtime') AND date(data_entrega) <= date('now', '+3 days', 'localtime') AND status != 'Concluida'"
        ).fetchall()
        for e in entregas_proximas:
            notifs.append({
                'tipo': 'entrega_proxima',
                'chave': f"entrega_proxima:{e['id']}",
                'prioridade': 'media',
                'icone': '📋',
                'msg': f"Entrega proxima: {e['cliente_nome']} em {e['data_entrega']}",
                'detalhes': e['descricao'] or '',
                'entrega_id': e['id'],
                'data': e['data_entrega']
            })

        # 3. Entregas atrasadas
        entregas_atrasadas = conexao.execute(
            "SELECT * FROM entregas_agendadas WHERE date(data_entrega) < date('now', 'localtime') AND status != 'Concluida'"
        ).fetchall()
        for e in entregas_atrasadas:
            notifs.append({
                'tipo': 'entrega_atrasada',
                'chave': f"entrega_atrasada:{e['id']}",
                'prioridade': 'critica',
                'icone': '🚨',
                'msg': f"ENTREGA ATRASADA: {e['cliente_nome']} (era {e['data_entrega']})",
                'detalhes': e['descricao'] or '',
                'entrega_id': e['id'],
                'data': e['data_entrega']
            })

        # 4. Clientes inativos (sem atualizacao ha mais de 90 dias)
        clientes_inativos = conexao.execute(
            "SELECT id, nome, cidade, atualizado_em FROM clientes WHERE atualizado_em < datetime('now', '-90 days', 'localtime') OR atualizado_em IS NULL ORDER BY atualizado_em ASC"
        ).fetchall()
        for c in clientes_inativos:
            dias = ''
            if c['atualizado_em']:
                try:
                    dt = datetime.strptime(c['atualizado_em'], '%Y-%m-%d %H:%M:%S')
                    dias = (datetime.now() - dt).days
                except Exception:
                    dias = '?'
            notifs.append({
                'tipo': 'cliente_inativo',
                'chave': f"cliente_inativo:{c['id']}",
                'prioridade': 'baixa',
                'icone': '👤',
                'msg': f"{c['nome']} sem atualizacao ha {dias} dias",
                'detalhes': c['cidade'] or '',
                'cliente_id': c['id'],
                'data': c['atualizado_em'] or ''
            })

        # 5. Pagamentos atrasados
        pagamentos_atrasados = conexao.execute(
            "SELECT p.*, c.nome as nome_cliente FROM pagamentos p LEFT JOIN clientes c ON p.cliente_id = c.id WHERE p.data_vencimento < date('now', 'localtime') AND p.status = 'Pendente'"
        ).fetchall()
        for p in pagamentos_atrasados:
            notifs.append({
                'tipo': 'pagamento_atrasado',
                'chave': f"pagamento_atrasado:{p['id']}",
                'prioridade': 'alta',
                'icone': '💰',
                'msg': f"Pagamento R$ {p['valor']:.2f} de {p['nome_cliente'] or p['cliente_nome']} atrasado!",
                'detalhes': f"Vencimento: {p['data_vencimento']}",
                'pagamento_id': p['id'],
                'data': p['data_vencimento']
            })

        # 6. Pagamentos vencendo hoje
        pagamentos_hoje = conexao.execute(
            "SELECT p.*, c.nome as nome_cliente FROM pagamentos p LEFT JOIN clientes c ON p.cliente_id = c.id WHERE date(p.data_vencimento) = date('now', 'localtime') AND p.status = 'Pendente'"
        ).fetchall()
        for p in pagamentos_hoje:
            notifs.append({
                'tipo': 'pagamento_hoje',
                'chave': f"pagamento_hoje:{p['id']}",
                'prioridade': 'media',
                'icone': '💳',
                'msg': f"Pagamento R$ {p['valor']:.2f} de {p['nome_cliente'] or p['cliente_nome']} vence HOJE!",
                'detalhes': '',
                'pagamento_id': p['id'],
                'data': p['data_vencimento']
            })

        # Marca quais ja foram lidas. Notificacoes lidas continuam na lista
        # (o fato subjacente nao mudou), mas nao contam para o badge.
        lidas = {linha['chave'] for linha in
                 conexao.execute('SELECT chave FROM notificacoes_lidas').fetchall()}

    for n in notifs:
        n['lida'] = n.get('chave') in lidas

    # Nao lidas primeiro; dentro de cada grupo, por prioridade.
    ordem = {'critica': 0, 'alta': 1, 'media': 2, 'baixa': 3}
    notifs.sort(key=lambda n: (n['lida'], ordem.get(n.get('prioridade', 'baixa'), 4)))
    return notifs


def marcar_notificacoes_lidas(chaves) -> int:
    """Marca as chaves informadas como lidas. Idempotente."""
    chaves = [str(c).strip() for c in (chaves or []) if str(c).strip()]
    if not chaves:
        return 0
    with conectar() as conexao:
        conexao.executemany(
            'INSERT OR IGNORE INTO notificacoes_lidas (chave) VALUES (?)',
            [(c,) for c in chaves],
        )
        return len(chaves)


def desmarcar_notificacoes_lidas(chaves=None) -> int:
    """Remove o estado de lida. Sem chaves, limpa todas."""
    with conectar() as conexao:
        if chaves is None:
            cursor = conexao.execute('DELETE FROM notificacoes_lidas')
        else:
            chaves = [str(c).strip() for c in chaves if str(c).strip()]
            if not chaves:
                return 0
            marcadores = ','.join('?' * len(chaves))
            cursor = conexao.execute(
                f'DELETE FROM notificacoes_lidas WHERE chave IN ({marcadores})', chaves)
        return cursor.rowcount
