import sqlite3
import os
import logging

import security
import notificacoes_db
from erp.core.auditoria import registrar_evento
from erp.core.schema_fallback import garantir_schema_fallback
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


def _filtro_de_busca(busca: str):
    """Devolve (fragmento_sql, parametros) para o termo de busca."""
    termo = (busca or '').strip()
    if not termo:
        return '', []
    like = f'%{termo}%'
    return ' AND (nome LIKE ? OR cidade LIKE ? OR bairro LIKE ?)', [like, like, like]


def contar_clientes(busca='') -> int:
    """Quantos clientes ativos atendem a busca. Base da paginacao."""
    filtro, parametros = _filtro_de_busca(busca)
    with conectar() as conexao:
        return conexao.execute(
            f'SELECT COUNT(*) FROM clientes WHERE ativo=1{filtro}', parametros  # noqa: S608 - fragmento constante do proprio codigo, nunca entrada do usuario
        ).fetchone()[0]


def listar_clientes(busca='', limite=None, deslocamento=0):
    """
    Clientes ativos, do mais recente para o mais antigo.

    `limite` e opcional, e a ausencia dele devolve TUDO -- de proposito. A
    sincronizacao do cache offline usa a lista como autoritativa: o que nao
    esta nela e podado. Se a paginacao virasse o padrao, a segunda pagina
    inteira seria tratada como "excluida no servidor" e sumiria do cache.

    Quem pagina (a tela de clientes) passa `limite` explicitamente e sabe que
    a resposta e parcial.
    """
    filtro, parametros = _filtro_de_busca(busca)
    sql = f'SELECT * FROM clientes WHERE ativo=1{filtro} ORDER BY id DESC'  # noqa: S608 - fragmento constante do proprio codigo, nunca entrada do usuario
    if limite is not None:
        sql += ' LIMIT ? OFFSET ?'
        parametros = parametros + [int(limite), int(deslocamento or 0)]

    with conectar() as conexao:
        linhas = conexao.execute(sql, parametros).fetchall()
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


# Quantos ids cabem num IN. O SQLite aceita 999 parametros por padrao (32766
# nas versoes recentes), e a exportacao vem de uma selecao feita a mao na tela
# -- ninguem marca mil clientes de uma vez. Cortar aqui evita que uma chamada
# construida em outro lugar derrube a consulta com "too many SQL variables".
MAX_IDS_POR_CONSULTA = 900


def listar_clientes_por_ids(ids):
    """
    Clientes ativos entre os ids informados, na ordem em que aparecem na lista.

    A exportacao carregava a BASE INTEIRA e filtrava em Python para ficar com N
    linhas -- custo proporcional ao total de clientes para exportar tres. Aqui o
    filtro vai ao banco, que e onde ha indice.

    A ordem da lista e preservada porque a planilha sai na ordem em que o
    operador selecionou; `ORDER BY id` reordenaria sem motivo.
    """
    numeros = []
    for bruto in (ids or []):
        try:
            numeros.append(int(bruto))
        except (TypeError, ValueError):
            continue
    if not numeros:
        return []

    marcadores = ','.join('?' * len(numeros[:MAX_IDS_POR_CONSULTA]))
    with conectar() as conexao:
        linhas = conexao.execute(
            f'SELECT * FROM clientes WHERE ativo=1 AND id IN ({marcadores})',  # noqa: S608 - fragmento constante do proprio codigo, nunca entrada do usuario
            numeros[:MAX_IDS_POR_CONSULTA],
        ).fetchall()

    por_id = {linha['id']: dict(linha) for linha in linhas}
    return [por_id[i] for i in numeros if i in por_id]


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


class ClienteTemVinculos(Exception):
    """
    Exclusao recusada porque o cliente tem pedido em aberto ou valor a receber.

    O blueprint traduz para 409: o pedido e valido, o cliente existe -- o que
    nao serve e o estado em que ele esta.
    """


# Status de parcela que representam dinheiro ainda a entrar.
#
# O codigo atual NUNCA grava 'Atrasado': o atraso e derivado do vencimento
# (`em_atraso`), nao declarado -- gravar seria manter duas verdades sobre o
# mesmo fato. 'Atrasado' entra aqui so para cobrir linha gravada por versao
# anterior: uma parcela vencida e mais devida, nao menos.
STATUS_A_RECEBER = ('Pendente', 'Atrasado')


def _vinculos_que_impedem_exclusao(conexao, id_cliente) -> tuple:
    """
    Conta o que ficaria orfao se o cliente fosse inativado agora.

    Pedido faturado e cancelado NAO contam: o primeiro ja produziu as parcelas
    (que sao contadas a parte) e o segundo nao espera mais nada. O que trava e
    trabalho em andamento -- rascunho, aberto, aprovado -- e dinheiro a receber.

    Devolve `(abertos, a_receber, orfas)`. As orfas sao contadas separado
    porque o operador NAO consegue resolve-las pela interface: as parcelas sao
    lidas e baixadas dentro do pedido que as emitiu, entao uma parcela sem
    `pedido_id` nao aparece em tela nenhuma. Nenhum caminho de escrita atual
    produz uma dessas -- `inserir_parcela` exige o pedido e e o unico INSERT em
    `pagamentos` do backend --, mas bancos anteriores a 1.5.0 tem linhas assim,
    criadas pelo cadastro avulso de pagamento que existia entao.

    Sem essa separacao o cliente ficava permanentemente inexcluivel e a
    mensagem mandava "conclua ou cancele" algo que ele nao tinha como achar.
    """
    marcadores = ", ".join("?" * len(STATUS_A_RECEBER))
    abertos = conexao.execute(
        "SELECT COUNT(*) FROM pedidos WHERE cliente_id = ? "
        "AND situacao NOT IN ('cancelado', 'faturado')", (id_cliente,)
    ).fetchone()[0]
    a_receber = conexao.execute(
        f"SELECT COUNT(*) FROM pagamentos WHERE cliente_id = ? "  # noqa: S608 - marcadores sao '?', o valor vai parametrizado
        f"AND status IN ({marcadores}) AND pedido_id IS NOT NULL",
        (id_cliente, *STATUS_A_RECEBER)
    ).fetchone()[0]
    orfas = conexao.execute(
        f"SELECT COUNT(*) FROM pagamentos WHERE cliente_id = ? "  # noqa: S608 - marcadores sao '?', o valor vai parametrizado
        f"AND status IN ({marcadores}) AND pedido_id IS NULL",
        (id_cliente, *STATUS_A_RECEBER)
    ).fetchone()[0]
    return abertos, a_receber, orfas


def excluir_cliente(id_cliente) -> int:
    """
    Inativa o cliente sem apagar seu historico ou vinculos empresariais.

    Recusa quando ha pedido em aberto ou parcela a receber. Antes disso a
    inativacao passava sempre, e o resultado era um limbo: o cliente sumia de
    todas as listas, mas o pedido faturado continuava aparecendo com o nome
    dele (que e snapshot em `pedidos.cliente_nome`) e as parcelas seguiam
    pendentes, invisiveis. Pior, tentar editar aquele pedido depois falhava com
    404 "Cliente nao encontrado", porque a validacao do cabecalho exige cliente
    ativo -- o pedido existia, era listado, e nao aceitava alteracao por um
    motivo que nao tinha nada a ver com ele.
    """
    with conectar() as conexao:
        antigo = conexao.execute(
            'SELECT * FROM clientes WHERE id=? AND ativo=1', (id_cliente,)
        ).fetchone()
        if not antigo:
            return 0

        abertos, a_receber, orfas = _vinculos_que_impedem_exclusao(conexao, id_cliente)
        if abertos or a_receber or orfas:
            partes = []
            if abertos:
                partes.append(f"{abertos} pedido(s) em aberto")
            if a_receber:
                partes.append(f"{a_receber} parcela(s) a receber")
            if orfas:
                partes.append(f"{orfas} parcela(s) antiga(s) sem pedido")
            mensagem = f"{antigo['nome']} tem {' e '.join(partes)}. "
            if abertos or a_receber:
                mensagem += "Conclua ou cancele antes de excluir."
            if orfas:
                # Sem esta frase o operador procura para sempre uma tela que
                # nao existe: parcela sem pedido nao aparece em lugar nenhum.
                mensagem = mensagem.rstrip() + (
                    " As parcelas sem pedido vieram de uma versao anterior e nao"
                    " aparecem na interface; peca suporte para encerra-las."
                )
            raise ClienteTemVinculos(mensagem.strip())

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
