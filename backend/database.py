import sqlite3
import os
import logging

import security
import asaas
import notificacoes_db
from erp.core import dinheiro
from erp.core.auditoria import registrar_evento
from erp.core.schema_fallback import garantir_schema_fallback
from erp.financeiro.servico_pagamentos import aplicar_evento_asaas
from notificacoes_db import MAX_NOTIFICACOES_POR_TIPO  # noqa: F401

log_db = logging.getLogger("adri.db")



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


# O journal_mode e propriedade do ARQUIVO, nao da conexao: uma vez gravado no
# header do banco, vale para todas as conexoes seguintes. Por isso e aplicado
# uma vez por caminho de banco, e nao a cada `conectar_bd()` -- executar o
# pragma em toda conexao custa uma escrita no header sem nenhum ganho.
_MODO_WAL_APLICADO: set = set()


def _garantir_modo_wal(conexao: sqlite3.Connection) -> None:
    """
    Liga o Write-Ahead Log.

    No modo padrao (`delete`), uma escrita bloqueia todas as leituras. O Flask
    roda com `threaded=True`, entao salvar um cliente enquanto o dashboard
    carrega significava uma das duas requisicoes esperando -- e, sob carga, o
    `database is locked` que ninguem consegue reproduzir depois.

    Com WAL, leitura e escrita convivem: quem le enxerga o ultimo estado
    consistente enquanto a escrita acontece em paralelo.

    `synchronous = NORMAL` e o par recomendado do WAL: em vez de sincronizar o
    disco a cada transacao, sincroniza no checkpoint. O risco que isso aceita e
    perder as ultimas transacoes numa queda de energia -- nao a corrupcao do
    banco, que o WAL continua evitando.
    """
    if DB_PATH in _MODO_WAL_APLICADO:
        return
    try:
        modo = conexao.execute("PRAGMA journal_mode = WAL").fetchone()[0]
        conexao.execute("PRAGMA synchronous = NORMAL")
        if str(modo).lower() != "wal":
            # Banco em pasta de rede nao aceita WAL. Nao e motivo para falhar:
            # o modo antigo continua correto, so mais lento sob concorrencia.
            log_db.warning("[BANCO] WAL indisponivel; journal_mode=%s", modo)
    except sqlite3.Error as erro:
        log_db.warning("[BANCO] Nao foi possivel ligar o WAL: %s", erro)
    _MODO_WAL_APLICADO.add(DB_PATH)


def conectar_bd() -> sqlite3.Connection:
    conexao = sqlite3.connect(DB_PATH, timeout=10)
    conexao.row_factory = sqlite3.Row
    # SQLite nao aplica foreign keys por padrao em cada nova conexao. Sem este
    # pragma, as constraints presentes no schema eram apenas decorativas.
    conexao.execute("PRAGMA foreign_keys = ON")
    conexao.execute("PRAGMA busy_timeout = 10000")
    _garantir_modo_wal(conexao)
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
        garantir_schema_fallback(conexao)


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
        novo = conexao.execute('SELECT * FROM clientes WHERE id=?', (cliente_id,)).fetchone()
        registrar_evento(
            conexao,
            acao="crm.cliente.criado",
            entidade="cliente",
            entidade_id=cliente_id,
            valores_novos=novo,
        )
        return cliente_id


def listar_clientes(busca=''):
    termo = (busca or '').strip()
    with conectar() as conexao:
        if termo:
            like = f'%{termo}%'
            linhas = conexao.execute(
                'SELECT * FROM clientes WHERE ativo=1 AND '
                '(nome LIKE ? OR cidade LIKE ? OR bairro LIKE ?) ORDER BY id DESC',
                (like, like, like),
            ).fetchall()
        else:
            linhas = conexao.execute(
                'SELECT * FROM clientes WHERE ativo=1 ORDER BY id DESC'
            ).fetchall()
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
        linha = conexao.execute(
            'SELECT * FROM clientes WHERE id=? AND ativo=1', (id_cliente,)
        ).fetchone()
        if not linha:
            return None
        return dict(linha)


def atualizar_cliente(id_cliente, nome, cep, rua, bairro, cidade, entrega_retirada, observacoes='') -> int:
    """
    Atualiza um cliente. Devolve 1 se atualizou, 0 se o id nao existe.

    O retorno existe para o endpoint distinguir os dois casos: antes o UPDATE
    em um id inexistente nao afetava linha nenhuma, mas a funcao seguia
    gravando historico e o PUT respondia 200 "Atualizado" -- alem de deixar
    linhas fantasma de ATUALIZACAO para clientes que nunca existiram.
    """
    with conectar() as conexao:
        antigo = conexao.execute(
            'SELECT * FROM clientes WHERE id=? AND ativo=1', (id_cliente,)
        ).fetchone()
        if not antigo:
            return 0
        conexao.execute(
            'UPDATE clientes SET nome=?, cep=?, rua=?, bairro=?, cidade=?, '
            'entrega_retirada=?, observacoes=?, '
            'atualizado_em=datetime(\'now\', \'localtime\') '
            'WHERE id=? AND ativo=1',
            (nome, cep, rua, bairro, cidade, entrega_retirada, observacoes, id_cliente),
        )
        detalhes_parts = []
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
        novo = conexao.execute('SELECT * FROM clientes WHERE id=?', (id_cliente,)).fetchone()
        registrar_evento(
            conexao,
            acao="crm.cliente.atualizado",
            entidade="cliente",
            entidade_id=id_cliente,
            valores_anteriores=antigo,
            valores_novos=novo,
        )
        return 1


def excluir_cliente(id_cliente) -> int:
    """Inativa o cliente sem apagar seu historico ou vinculos empresariais."""
    with conectar() as conexao:
        antigo = conexao.execute(
            'SELECT * FROM clientes WHERE id=? AND ativo=1', (id_cliente,)
        ).fetchone()
        if not antigo:
            return 0
        cursor = conexao.execute(
            "UPDATE clientes SET ativo=0, excluido_em=datetime('now', 'localtime'), "
            "atualizado_em=datetime('now', 'localtime') WHERE id=? AND ativo=1",
            (id_cliente,),
        )
        if antigo and cursor.rowcount > 0:
            conexao.execute(
                'INSERT INTO historico (cliente_id, cliente_nome, acao, detalhes) VALUES (?, ?, ?, ?)',
                (id_cliente, antigo['nome'], 'EXCLUSAO', f"Cliente excluído: {antigo['nome']}, {antigo['cidade'] or ''}, {antigo['bairro'] or ''}"),
            )
            novo = conexao.execute('SELECT * FROM clientes WHERE id=?', (id_cliente,)).fetchone()
            registrar_evento(
                conexao,
                acao="crm.cliente.inativado",
                entidade="cliente",
                entidade_id=id_cliente,
                valores_anteriores=antigo,
                valores_novos=novo,
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
            existente = conexao.execute(
                'SELECT id FROM clientes WHERE nome=? AND cep=? AND ativo=1', (nome, cep)
            ).fetchone()
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
            novo = conexao.execute('SELECT * FROM clientes WHERE id=?', (cliente_id,)).fetchone()
            registrar_evento(
                conexao,
                acao="crm.cliente.importado",
                entidade="cliente",
                entidade_id=cliente_id,
                valores_novos=novo,
                contexto_extra={"operacao": "importacao_em_lote"},
            )
            sucessos += 1
    return {"sucessos": sucessos, "duplicados": duplicados, "erros": erros}


def excluir_sessao():
    with conectar() as conexao:
        conexao.execute('DELETE FROM sessao')


def salvar_sessao(token, conta, refresh_token=None, expira_em=None):
    """
    Grava a sessao Microsoft, substituindo a anterior.

    `refresh_token` e `expira_em` sao opcionais para nao quebrar chamadas
    antigas de dois argumentos; quando ausentes, a sessao se comporta como
    antes -- vale ate o Graph recusar o token.
    """
    with conectar() as conexao:
        conexao.execute('DELETE FROM sessao')
        conexao.execute(
            'INSERT INTO sessao (token, conta, refresh_token, expira_em) VALUES (?, ?, ?, ?)',
            (
                security.cifrar(token),
                conta,
                # O refresh_token e credencial de longa duracao: vale mais que
                # o access_token e e cifrado pelo mesmo caminho.
                security.cifrar(refresh_token) if refresh_token else None,
                int(expira_em) if expira_em else None,
            ),
        )


def _decifrar_campo(valor):
    """Decifra tolerando o formato antigo (Fernet) alem do atual."""
    if not valor:
        return None
    claro = security.decifrar(valor)
    if claro is None:
        claro = security.fernet_decifrar(valor)
    return claro


def obter_sessao():
    with conectar() as conexao:
        linha = conexao.execute(
            'SELECT token, conta, refresh_token, expira_em FROM sessao LIMIT 1'
        ).fetchone()
        if not linha:
            return None

        token_decifrado = _decifrar_campo(linha['token'])
        if token_decifrado is None:
            log_db.warning("[SESSAO] Falha ao decifrar token da sessao.")
            return None

        return {
            "token": token_decifrado,
            "conta": linha["conta"],
            # Ausente nas sessoes gravadas antes desta coluna existir.
            "refresh_token": _decifrar_campo(linha["refresh_token"]),
            "expira_em": linha["expira_em"],
        }


def atualizar_token_sessao(token, expira_em, refresh_token=None):
    """
    Troca o access_token da sessao vigente sem tocar na conta.

    A Microsoft pode devolver um refresh_token novo na renovacao (rotacao);
    quando devolve, ele substitui o anterior. Quando nao devolve, o antigo
    continua valendo e nao pode ser apagado.
    """
    with conectar() as conexao:
        if refresh_token:
            conexao.execute(
                'UPDATE sessao SET token=?, expira_em=?, refresh_token=?',
                (security.cifrar(token), int(expira_em), security.cifrar(refresh_token)),
            )
        else:
            conexao.execute(
                'UPDATE sessao SET token=?, expira_em=?',
                (security.cifrar(token), int(expira_em)),
            )


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


def salvar_pagamento(cliente_id, cliente_nome, valor, descricao, data_vencimento,
                     tipo_pagamento='Pix', status='Pendente', data_pagamento='',
                     valor_centavos=None):
    """
    Cria um novo pagamento e retorna o ID.

    `status`/`data_pagamento` sao parametros porque a tela de recebimento
    registra dinheiro que JA entrou. Fixar 'Pendente' aqui fazia esse
    lancamento nascer vencido e ser contado como atrasado no mesmo instante.

    `valor_centavos` e a fonte de verdade quando informado -- e o caso do
    faturamento de pedido, que ja tem o valor rateado em centavos exatos e nao
    deve passa-lo por float. Quando so `valor` chega (tela de recebimento
    avulso), os centavos sao derivados dele.
    """
    centavos = dinheiro.para_centavos(valor) if valor_centavos is None else int(valor_centavos)
    valor = round(centavos / 100, 2)

    with conectar() as conexao:
        conexao.execute(
            'INSERT INTO pagamentos (cliente_id, cliente_nome, valor, valor_centavos, descricao, status, data_vencimento, tipo_pagamento, data_pagamento) '
            'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
            (cliente_id, cliente_nome, valor, centavos, descricao, status, data_vencimento, tipo_pagamento, data_pagamento),
        )
        pagamento_id = conexao.execute('SELECT last_insert_rowid()').fetchone()[0]
        acao = 'Recebimento registrado' if status == 'Recebido' else 'Cobranca criada'
        conexao.execute(
            'INSERT INTO historico (cliente_id, cliente_nome, acao, detalhes) VALUES (?, ?, ?, ?)',
            (cliente_id, cliente_nome, 'PAGAMENTO', f'{acao}: R$ {valor:.2f} ({tipo_pagamento})'),
        )
        novo = conexao.execute('SELECT * FROM pagamentos WHERE id=?', (pagamento_id,)).fetchone()
        registrar_evento(
            conexao,
            acao="financeiro.recebivel.criado",
            entidade="pagamento",
            entidade_id=pagamento_id,
            valores_novos=novo,
        )
        return pagamento_id


def atualizar_pagamento(pagamento_id, **kwargs):
    """Atualiza campos de um pagamento existente."""
    campos_permitidos = {
        'status', 'data_pagamento', 'asaas_payment_id', 'pix_payload',
        'pix_qr_code', 'boleto_url', 'nosso_numero', 'descricao',
        'valor', 'valor_centavos', 'data_vencimento', 'tipo_pagamento',
        'cliente_nome', 'asaas_external_reference', 'asaas_emissao_estado',
    }
    campos = {k: v for k, v in kwargs.items() if k in campos_permitidos and v is not None}
    if not campos:
        return 0

    # As duas colunas de dinheiro andam juntas. Deixar `valor` mudar sozinho
    # faria `valor_centavos` guardar o numero antigo -- e a divergencia seria
    # silenciosa ate alguem comparar os dois em um relatorio.
    if 'valor' in campos and 'valor_centavos' not in campos:
        campos['valor_centavos'] = dinheiro.para_centavos(campos['valor'])
    elif 'valor_centavos' in campos and 'valor' not in campos:
        campos['valor'] = round(int(campos['valor_centavos']) / 100, 2)
    sets = ', '.join(f'{k}=?' for k in campos)
    vals = list(campos.values()) + [pagamento_id]
    with conectar() as conexao:
        antigo = conexao.execute(
            'SELECT * FROM pagamentos WHERE id=?', (pagamento_id,)
        ).fetchone()
        if not antigo:
            return 0
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
        if linhas:
            novo = conexao.execute(
                'SELECT * FROM pagamentos WHERE id=?', (pagamento_id,)
            ).fetchone()
            registrar_evento(
                conexao,
                acao="financeiro.recebivel.atualizado",
                entidade="pagamento",
                entidade_id=pagamento_id,
                valores_anteriores=antigo,
                valores_novos=novo,
            )
        return linhas


def registrar_observacao_de_pagamento(pagamento_id: int, observacao: str) -> None:
    """
    Anexa uma nota ao historico e a auditoria do pagamento.

    Usado quando uma decisao humana contraria o que o sistema apuraria
    sozinho -- confirmar na mao uma cobranca que o gateway ainda mostra em
    aberto, por exemplo. Sem o registro, o numero fica certo na tela e
    inexplicavel depois.
    """
    with conectar() as conexao:
        pagamento = conexao.execute(
            'SELECT * FROM pagamentos WHERE id=?', (pagamento_id,)
        ).fetchone()
        if not pagamento:
            return
        conexao.execute(
            'INSERT INTO historico (cliente_id, cliente_nome, acao, detalhes) '
            'VALUES (?, ?, ?, ?)',
            (pagamento['cliente_id'], pagamento['cliente_nome'], 'PAGAMENTO',
             observacao[:500]),
        )
        registrar_evento(
            conexao,
            acao="financeiro.recebivel.observacao_manual",
            entidade="pagamento",
            entidade_id=pagamento_id,
            valores_novos={"observacao": observacao[:500]},
        )


def excluir_pagamento(pagamento_id) -> int:
    """
    Cancela uma cobranca pendente marcando-a como 'Cancelado'.

    Nao apaga a linha, e a mudanca e deliberada. Registro financeiro apagado
    e registro que nao existe: some do extrato, some da conferencia com o
    Asaas (que continua conhecendo aquela cobranca pelo `asaas_payment_id`) e
    some da propria trilha de auditoria, que passa a ter um evento de
    cancelamento apontando para um id sem destino.

    'Cancelado' ja era um status do dominio -- as metricas do dashboard e os
    filtros da tela ja o tratavam. O que faltava era o caminho de cancelamento
    usa-lo.

    O nome da funcao fica como esta por ser o contrato que a rota DELETE e os
    chamadores conhecem; o docstring e o que descreve o comportamento.
    """
    with conectar() as conexao:
        pagamento = conexao.execute('SELECT * FROM pagamentos WHERE id=?', (pagamento_id,)).fetchone()
        cursor = conexao.execute(
            "UPDATE pagamentos SET status='Cancelado' WHERE id=? AND status='Pendente'",
            (pagamento_id,),
        )
        if pagamento and cursor.rowcount > 0:
            conexao.execute(
                'INSERT INTO historico (cliente_id, cliente_nome, acao, detalhes) VALUES (?, ?, ?, ?)',
                (pagamento['cliente_id'], pagamento['cliente_nome'], 'PAGAMENTO',
                 f'Cobranca cancelada: R$ {pagamento["valor"]:.2f}'),
            )
            novo = conexao.execute(
                'SELECT * FROM pagamentos WHERE id=?', (pagamento_id,)
            ).fetchone()
            registrar_evento(
                conexao,
                acao="financeiro.recebivel.cancelado",
                entidade="pagamento",
                entidade_id=pagamento_id,
                valores_anteriores=pagamento,
                valores_novos=novo,
            )
        return cursor.rowcount


def atualizar_pagamento_por_asaas(
    asaas_payment_id: str,
    novo_status: str,
    *,
    preencher_data_pagamento: bool = False,
    status_anterior: str | None = None,
) -> int:
    return aplicar_evento_asaas(
        conectar,
        asaas_payment_id,
        novo_status,
        preencher_data_pagamento=preencher_data_pagamento,
        status_anterior=status_anterior,
    )


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
            registrar_evento(
                conexao,
                acao="crm.cliente.integracao_asaas_vinculada",
                entidade="cliente_asaas",
                entidade_id=cliente_id,
                valores_novos={
                    "cliente_id": cliente_id,
                    "asaas_customer_id": asaas_id,
                },
            )
        return asaas_id


# Cobrancas que ainda representam dinheiro a entrar. 'Atrasado' continua
# sendo um valor a receber: vencer nao quita nem cancela a cobranca. Os
# dois blocos de metricas do dashboard leem daqui para nao divergirem.
_STATUS_A_RECEBER = "('Pendente', 'Atrasado')"


def obter_metricas_pagamentos():
    """Retorna metricas de pagamentos para o dashboard."""
    with conectar() as conexao:
        total_recebido = conexao.execute(
            "SELECT COALESCE(SUM(valor), 0) FROM pagamentos WHERE status='Recebido'"
        ).fetchone()[0]
        total_pendente = conexao.execute(
            "SELECT COALESCE(SUM(valor), 0) FROM pagamentos "
            f"WHERE status IN {_STATUS_A_RECEBER}"
        ).fetchone()[0]
        total_atrasado = conexao.execute(
            "SELECT COALESCE(SUM(valor), 0) FROM pagamentos "
            f"WHERE status IN {_STATUS_A_RECEBER} "
            "AND data_vencimento != '' AND date(data_vencimento) < date('now', 'localtime')"
        ).fetchone()[0]
        qtd_recebido = conexao.execute(
            "SELECT COUNT(*) FROM pagamentos WHERE status='Recebido'"
        ).fetchone()[0]
        qtd_pendente = conexao.execute(
            "SELECT COUNT(*) FROM pagamentos "
            f"WHERE status IN {_STATUS_A_RECEBER}"
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
            "SELECT COALESCE(SUM(valor), 0) FROM pagamentos "
            f"WHERE status IN {_STATUS_A_RECEBER}"
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
            "SELECT entrega_retirada, COUNT(*) as total FROM clientes "
            "WHERE ativo=1 GROUP BY entrega_retirada"
        ).fetchall()
        return {row['entrega_retirada']: row['total'] for row in linhas}


def obter_dados_grafico_cidades(limite=10):
    """Retorna top N cidades com mais clientes para gráfico de barras."""
    with conectar() as conexao:
        linhas = conexao.execute(
            "SELECT cidade, COUNT(*) as total FROM clientes WHERE ativo=1 "
            "AND cidade IS NOT NULL AND cidade != '' "
            "GROUP BY cidade ORDER BY total DESC LIMIT ?",
            (limite,)
        ).fetchall()
        return [(row['cidade'], row['total']) for row in linhas]


def obter_dados_grafico_timeline(dias=30):
    """Retorna cadastros por dia nos últimos N dias para gráfico de linha."""
    with conectar() as conexao:
        linhas = conexao.execute(
            "SELECT date(criado_em) as dia, COUNT(*) as total FROM clientes "
            "WHERE ativo=1 AND criado_em >= date('now', '-' || ? || ' days', 'localtime') "
            "GROUP BY dia ORDER BY dia",
            (dias,)
        ).fetchall()
        return [(row['dia'], row['total']) for row in linhas]


def obter_clientes_para_mapa():
    """Retorna clientes individuais com CEP para geolocalizacao no mapa."""
    with conectar() as conexao:
        linhas = conexao.execute(
            "SELECT id, nome, cep, rua, bairro, cidade, entrega_retirada "
            "FROM clientes WHERE ativo=1 AND cep IS NOT NULL AND cep != '' ORDER BY id DESC"
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
    query = 'SELECT * FROM clientes WHERE ativo=1'
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
            "FROM clientes WHERE ativo=1 AND cidade IS NOT NULL AND cidade != '' "
            "GROUP BY cidade ORDER BY total DESC"
        ).fetchall()
    return [{
        "cidade": row["cidade"], "total": row["total"],
        "entregas": row["entregas"], "retiradas": row["retiradas"]
    } for row in linhas]


def obter_ultimos_clientes(limite=5):
    """Retorna os últimos N clientes cadastrados."""
    with conectar() as conexao:
        linhas = conexao.execute(
            'SELECT id, nome, cidade, bairro, entrega_retirada, criado_em '
            'FROM clientes WHERE ativo=1 ORDER BY id DESC LIMIT ?',
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
            total_clientes = conexao.execute(
                'SELECT COUNT(*) FROM clientes WHERE ativo=1'
            ).fetchone()[0] or 0
            total_entrega = conexao.execute(
                "SELECT COUNT(*) FROM clientes WHERE ativo=1 AND entrega_retirada='Entrega'"
            ).fetchone()[0] or 0
            total_retirada = conexao.execute(
                "SELECT COUNT(*) FROM clientes WHERE ativo=1 AND entrega_retirada='Retirada'"
            ).fetchone()[0] or 0
            try:
                cadastros_30d = conexao.execute(
                    "SELECT COUNT(*) FROM clientes WHERE ativo=1 AND "
                    "criado_em >= datetime('now', '-30 days', 'localtime')"
                ).fetchone()[0] or 0
            except Exception:
                cadastros_30d = 0
            return {
                "total_clientes": total_clientes,
                "total_entrega": total_entrega,
                "total_retirada": total_retirada,
                "cadastros_30d": cadastros_30d,
            }
    except Exception:
        log_db.exception("Erro ao obter metricas do dashboard")
        return {"total_clientes": 0, "total_entrega": 0, "total_retirada": 0, "cadastros_30d": 0}


# -----------------------------------------------------------------------------
# Entregas Agendadas
# -----------------------------------------------------------------------------
def agendar_entrega(cliente_id, cliente_nome, data_entrega, hora_entrega='', descricao='',
                    pedido_id=None):
    with conectar() as conexao:
        conexao.execute(
            'INSERT INTO entregas_agendadas (cliente_id, cliente_nome, data_entrega, hora_entrega, descricao, pedido_id) VALUES (?, ?, ?, ?, ?, ?)',
            (cliente_id, cliente_nome, data_entrega, hora_entrega, descricao, pedido_id),
        )
        entrega_id = conexao.execute('SELECT last_insert_rowid()').fetchone()[0]
        novo = conexao.execute(
            'SELECT * FROM entregas_agendadas WHERE id=?', (entrega_id,)
        ).fetchone()
        registrar_evento(
            conexao,
            acao="operacional.entrega.agendada",
            entidade="entrega",
            entidade_id=entrega_id,
            valores_novos=novo,
        )
        return entrega_id


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
        antigo = conexao.execute(
            'SELECT * FROM entregas_agendadas WHERE id=?', (entrega_id,)
        ).fetchone()
        if not antigo:
            return 0
        conexao.execute('UPDATE entregas_agendadas SET status=? WHERE id=?', (novo_status, entrega_id))
        linhas = conexao.execute('SELECT changes()').fetchone()[0]
        if linhas:
            novo = conexao.execute(
                'SELECT * FROM entregas_agendadas WHERE id=?', (entrega_id,)
            ).fetchone()
            registrar_evento(
                conexao,
                acao="operacional.entrega.status_alterado",
                entidade="entrega",
                entidade_id=entrega_id,
                valores_anteriores=antigo,
                valores_novos=novo,
            )
        return linhas


# ---------------------------------------------------------------------------
# Notificacoes
#
# A implementacao vive em `notificacoes_db.py`. Os involucros abaixo existem
# porque os blueprints e os testes chamam `database.obter_notificacoes(...)`, e
# sao eles que injetam a fabrica de conexao deste modulo -- mantendo valido o
# ponto de extensao que os testes usam ao substituir `database.DB_PATH`.
# ---------------------------------------------------------------------------
def obter_notificacoes():
    """Gera lista inteligente de notificacoes do sistema."""
    return notificacoes_db.obter_notificacoes(conectar)


def marcar_notificacoes_lidas(chaves) -> int:
    """Marca as chaves informadas como lidas. Idempotente."""
    return notificacoes_db.marcar_notificacoes_lidas(conectar, chaves)


def desmarcar_notificacoes_lidas(chaves=None) -> int:
    """Volta notificacoes para nao lidas. Sem chaves, limpa todas."""
    return notificacoes_db.desmarcar_notificacoes_lidas(conectar, chaves)
