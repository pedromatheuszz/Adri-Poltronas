"""
Notificacoes derivadas do estado do banco.

Extraido de `database.py` para manter aquele arquivo abaixo do teto de 800
linhas adotado no projeto. As notificacoes nao sao armazenadas: cada categoria
e uma consulta sobre entregas e clientes, e so o estado de "lida"
e persistido.

Este modulo NAO importa `database`. A fabrica de conexao chega como parametro
`conectar`, e `database` apenas repassa a sua. Uma importacao mutua aqui
quebrava o app de verdade sem quebrar os testes: bastava um entrypoint importar
`backend.database` enquanto a suite importava `database` como modulo de topo --
o segundo carregamento do mesmo arquivo, agora sob outro nome, estourava
ImportError no meio da inicializacao.
"""
import logging
from datetime import datetime

import validators

_log = logging.getLogger("adri.notificacoes")


# Teto por categoria de notificacao.
#
# As notificacoes sao derivadas de consultas abertas. A de clientes inativos
# nao tinha limite nenhum: cresce com a base inteira, e numa base madura o
# painel virava milhares de itens -- remontados a cada atualizacao, com o
# endpoint devolvendo todos de uma vez.
MAX_NOTIFICACOES_POR_TIPO = 50

# Status que encerram uma entrega: nao ha mais nada a avisar sobre ela.
# A lista canonica vive em validators.py, junto com os demais conjuntos de
# opcoes; aqui ela so vira literal SQL.
_STATUS_ENCERRADOS = "('" + "', '".join(validators.STATUS_ENTREGA_ENCERRADOS) + "')"


def _dias_desde(data_hora):
    """
    Dias decorridos desde `data_hora` ('AAAA-MM-DD HH:MM:SS').

    Devolve None quando o valor esta vazio ou nao e uma data legivel --
    o chamador precisa distinguir esse caso para nao montar um texto sem
    numero nenhum ("sem atualizacao ha  dias").
    """
    if not data_hora:
        return None
    try:
        return (datetime.now() - datetime.strptime(str(data_hora), '%Y-%m-%d %H:%M:%S')).days
    except (TypeError, ValueError):
        return None


def expurgar_lidas_orfas(conexao) -> int:
    """
    Remove marcas de "lida" que nao correspondem mais a notificacao nenhuma.

    A tabela `notificacoes_lidas` so crescia. Cada entrega e cada cliente que o
    operador dispensasse deixava uma linha para sempre -- inclusive depois de a
    entrega ser concluida ou o cliente ser inativado, quando a notificacao
    correspondente ja nao e gerada e a marca perdeu qualquer funcao.

    O criterio e a existencia do FATO, nao a idade da marca. Um prazo em dias
    seria arbitrario e traria o defeito oposto: uma entrega ainda atrasada e
    ainda dispensada voltaria a aparecer sozinha ao vencer o prazo, e o
    operador nao entenderia por que.

    As chaves tem a forma `<tipo>:<id>`, montadas em `obter_notificacoes`.
    Sobra a marca quando o registro nao existe mais, ou quando a entrega ja
    esta encerrada.
    """
    cursor = conexao.execute(
        f"""DELETE FROM notificacoes_lidas
             WHERE (
                    chave LIKE 'entrega_%'
                AND CAST(substr(chave, instr(chave, ':') + 1) AS INTEGER) NOT IN (
                        SELECT id FROM entregas_agendadas
                         WHERE status NOT IN {_STATUS_ENCERRADOS})
             )
                OR (
                    chave LIKE 'cliente_inativo:%'
                AND CAST(substr(chave, instr(chave, ':') + 1) AS INTEGER) NOT IN (
                        SELECT id FROM clientes WHERE ativo = 1)
             )"""
    )
    return cursor.rowcount


def obter_notificacoes(conectar):
    """Gera lista inteligente de notificacoes do sistema."""
    notifs = []
    with conectar() as conexao:
        # O expurgo acontece aqui porque e o unico ponto que roda com
        # regularidade e ja tem a conexao aberta -- e porque e exatamente o
        # momento em que a lista de notificacoes vigentes esta sendo
        # recalculada. Uma rotina propria precisaria de agendador.
        removidas = expurgar_lidas_orfas(conexao)
        if removidas:
            _log.info("[NOTIFICACOES] %s marcas de lida sem notificacao removidas.",
                      removidas)

        # 1. Entregas agendadas para hoje
        entregas_hoje = conexao.execute(
            "SELECT * FROM entregas_agendadas WHERE date(data_entrega) = date('now', 'localtime') "
            f"AND status NOT IN {_STATUS_ENCERRADOS} ORDER BY hora_entrega LIMIT ?",
            (MAX_NOTIFICACOES_POR_TIPO,)
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
            "SELECT * FROM entregas_agendadas WHERE date(data_entrega) > date('now', 'localtime') "
            "AND date(data_entrega) <= date('now', '+3 days', 'localtime') "
            f"AND status NOT IN {_STATUS_ENCERRADOS} "
            "ORDER BY data_entrega LIMIT ?", (MAX_NOTIFICACOES_POR_TIPO,)
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
            "SELECT * FROM entregas_agendadas WHERE date(data_entrega) < date('now', 'localtime') "
            f"AND status NOT IN {_STATUS_ENCERRADOS} ORDER BY data_entrega LIMIT ?",
            (MAX_NOTIFICACOES_POR_TIPO,)
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
            "SELECT id, nome, cidade, atualizado_em FROM clientes "
            "WHERE ativo=1 AND (atualizado_em < datetime('now', '-90 days', 'localtime') "
            "OR atualizado_em IS NULL) "
            "ORDER BY atualizado_em ASC LIMIT ?", (MAX_NOTIFICACOES_POR_TIPO,)
        ).fetchall()
        for c in clientes_inativos:
            dias = _dias_desde(c['atualizado_em'])
            if dias is None:
                mensagem = f"{c['nome']} sem data de ultima atualizacao"
            else:
                plural = 'dia' if dias == 1 else 'dias'
                mensagem = f"{c['nome']} sem atualizacao ha {dias} {plural}"
            notifs.append({
                'tipo': 'cliente_inativo',
                'chave': f"cliente_inativo:{c['id']}",
                'prioridade': 'baixa',
                'icone': '👤',
                'msg': mensagem,
                'detalhes': c['cidade'] or '',
                'cliente_id': c['id'],
                'data': c['atualizado_em'] or ''
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


def marcar_notificacoes_lidas(conectar, chaves) -> int:
    """
    Marca as chaves informadas como lidas. Idempotente.

    Devolve quantas foram REALMENTE inseridas, e nao o tamanho da entrada: o
    INSERT OR IGNORE descarta as que ja estavam la, entao devolver len(chaves)
    fazia a interface relatar "12 marcadas" quando nada mudou.
    """
    # `None` precisa cair fora antes do str(): str(None) e 'None', uma string
    # verdadeira, que era gravada como se fosse uma chave legitima.
    chaves = [str(c).strip() for c in (chaves or []) if c is not None and str(c).strip()]
    if not chaves:
        return 0
    with conectar() as conexao:
        antes = conexao.execute('SELECT COUNT(*) FROM notificacoes_lidas').fetchone()[0]
        conexao.executemany(
            'INSERT OR IGNORE INTO notificacoes_lidas (chave) VALUES (?)',
            [(c,) for c in chaves],
        )
        depois = conexao.execute('SELECT COUNT(*) FROM notificacoes_lidas').fetchone()[0]
        return depois - antes


def desmarcar_notificacoes_lidas(conectar, chaves=None) -> int:
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
