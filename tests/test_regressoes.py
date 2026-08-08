"""
Testes de regressão para os defeitos encontrados na auditoria técnica.

Cada teste referencia o item do relatório que o originou. Todos falham
na versão anterior do código.
"""
import os
import sys
import json
import tempfile
from datetime import timedelta

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

import asaas  # noqa: E402
import config  # noqa: E402
import database  # noqa: E402
import planilha  # noqa: E402
import app as app_module  # noqa: E402

# O test client do Flask atende como host 'localhost' (sem porta). A checagem
# de origem deriva do host da requisicao, entao a origem valida acompanha isso.
ORIGEM_LOCAL = 'http://localhost'


@pytest.fixture
def client():
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name

    original = database.DB_PATH
    database.DB_PATH = db_path
    app_module.app.config['TESTING'] = True
    with app_module.app.app_context():
        database.criar_tabela()

    yield app_module.app.test_client()

    database.DB_PATH = original
    os.unlink(db_path)


def _criar_cliente_com_pagamento(client, data_vencimento):
    """Cria um cliente e uma cobrança pendente com o vencimento informado."""
    client.post('/api/clientes', headers={'Origin': ORIGEM_LOCAL},
        data=json.dumps({
            "nome": "Cliente Teste", "cep": "12345-678", "rua": "Rua Teste",
            "bairro": "Centro", "cidade": "São Paulo", "entrega_retirada": "Entrega",
        }), content_type='application/json')
    cliente_id = json.loads(client.get('/api/clientes').data)[0]['id']
    database.salvar_pagamento(cliente_id, "Cliente Teste", 250.00, "Poltrona", data_vencimento)
    return cliente_id


# -----------------------------------------------------------------------------
# A5 - sqlite3.Row nao tem .get(), o que derrubava TODAS as notificacoes
# -----------------------------------------------------------------------------
def test_notificacoes_com_pagamento_atrasado_nao_quebra(client):
    _criar_cliente_com_pagamento(client, '2020-01-01')

    resposta = client.get('/api/notificacoes')

    assert resposta.status_code == 200
    dados = json.loads(resposta.data)
    assert 'erro' not in dados, f"Notificacoes falharam: {dados.get('erro')}"
    tipos = [n['tipo'] for n in dados['notificacoes']]
    assert 'pagamento_atrasado' in tipos


def test_notificacao_de_atraso_usa_nome_do_cliente(client):
    _criar_cliente_com_pagamento(client, '2020-01-01')

    notificacoes = json.loads(client.get('/api/notificacoes').data)['notificacoes']

    atrasado = next(n for n in notificacoes if n['tipo'] == 'pagamento_atrasado')
    assert 'Cliente Teste' in atrasado['msg']


def test_notificacoes_sobrevivem_a_pagamento_sem_cliente_correspondente(client):
    """O LEFT JOIN devolve nome_cliente NULL quando o cliente nao existe mais."""
    database.salvar_pagamento(9999, "Cliente Removido", 100.00, "Orfao", '2020-01-01')

    resposta = client.get('/api/notificacoes')

    assert resposta.status_code == 200
    dados = json.loads(resposta.data)
    assert 'erro' not in dados
    atrasado = next(n for n in dados['notificacoes'] if n['tipo'] == 'pagamento_atrasado')
    assert 'Cliente Removido' in atrasado['msg']


# -----------------------------------------------------------------------------
# M1 - CSRF: POST cross-site em endpoints que nao leem corpo
# -----------------------------------------------------------------------------
def test_confirmar_pagamento_recusa_origem_externa(client):
    cliente_id = _criar_cliente_com_pagamento(client, '2030-01-01')
    pagamento_id = database.listar_pagamentos(cliente_id=cliente_id)[0]['id']

    resposta = client.post(f'/api/pagamentos/{pagamento_id}/confirmar',
                           headers={'Origin': 'https://site-malicioso.example'})

    assert resposta.status_code == 403
    assert database.obter_pagamento_por_id(pagamento_id)['status'] == 'Pendente'


def test_confirmar_pagamento_aceita_origem_local(client):
    cliente_id = _criar_cliente_com_pagamento(client, '2030-01-01')
    pagamento_id = database.listar_pagamentos(cliente_id=cliente_id)[0]['id']

    resposta = client.post(f'/api/pagamentos/{pagamento_id}/confirmar',
                           headers={'Origin': ORIGEM_LOCAL})

    assert resposta.status_code == 200
    assert database.obter_pagamento_por_id(pagamento_id)['status'] == 'Recebido'


def test_referer_externo_tambem_e_recusado(client):
    resposta = client.post('/api/auth/logout',
                           headers={'Referer': 'https://site-malicioso.example/pagina'})
    assert resposta.status_code == 403


def test_get_nao_e_afetado_pela_checagem_de_origem(client):
    resposta = client.get('/api/clientes', headers={'Origin': 'https://qualquer.example'})
    assert resposta.status_code == 200


def test_loopback_alias_e_aceito_no_mesmo_host(client):
    """127.0.0.1 e localhost sao a mesma maquina, mas origens distintas no navegador."""
    resposta = client.post('/api/auth/logout', headers={'Origin': 'http://127.0.0.1'})
    assert resposta.status_code == 200


def test_checagem_de_origem_acompanha_a_porta_do_servidor(client):
    """
    A lista de origens e derivada do host da requisicao, e nao fixada em :5000.
    Uma lista fixa faria o proprio frontend levar 403 em qualquer outra porta.
    """
    aceita = client.post('/api/auth/logout',
                         headers={'Origin': 'http://localhost:8080', 'Host': 'localhost:8080'})
    assert aceita.status_code == 200

    recusada = client.post('/api/auth/logout',
                           headers={'Origin': 'http://localhost:9999', 'Host': 'localhost:8080'})
    assert recusada.status_code == 403


def test_sem_origin_e_sem_referer_e_permitido(client):
    """Clientes locais (curl, scripts) nao sao navegadores e nao sofrem CSRF."""
    assert client.post('/api/auth/logout').status_code == 200


# -----------------------------------------------------------------------------
# A2 - webhook Asaas: token estatico `asaas-access-token`, nao HMAC
# -----------------------------------------------------------------------------
def _post_webhook(client, headers=None):
    return client.post('/api/pagamentos/webhook',
                       data=json.dumps({"event": "PAYMENT_RECEIVED", "payment": {"id": "pay_1"}}),
                       content_type='application/json', headers=headers or {})


def test_webhook_recusa_quando_token_nao_configurado(client, monkeypatch):
    monkeypatch.setattr(config, 'ASAAS_WEBHOOK_TOKEN', '')
    assert _post_webhook(client, {'asaas-access-token': 'qualquer'}).status_code == 503


def test_webhook_recusa_token_invalido(client, monkeypatch):
    monkeypatch.setattr(config, 'ASAAS_WEBHOOK_TOKEN', 'token_correto')
    assert _post_webhook(client, {'asaas-access-token': 'token_errado'}).status_code == 401


def test_webhook_recusa_requisicao_sem_header(client, monkeypatch):
    monkeypatch.setattr(config, 'ASAAS_WEBHOOK_TOKEN', 'token_correto')
    assert _post_webhook(client).status_code == 401


def test_webhook_aceita_token_valido_e_confirma_pagamento(client, monkeypatch):
    monkeypatch.setattr(config, 'ASAAS_WEBHOOK_TOKEN', 'token_correto')
    cliente_id = _criar_cliente_com_pagamento(client, '2030-01-01')
    pagamento_id = database.listar_pagamentos(cliente_id=cliente_id)[0]['id']
    database.atualizar_pagamento(pagamento_id, asaas_payment_id='pay_1')

    resposta = _post_webhook(client, {'asaas-access-token': 'token_correto'})

    assert resposta.status_code == 200
    assert database.obter_pagamento_por_id(pagamento_id)['status'] == 'Recebido'


# -----------------------------------------------------------------------------
# A1 - asaas lia os.environ no import, antes do load_dotenv
# -----------------------------------------------------------------------------
def test_asaas_le_configuracao_em_tempo_de_chamada(monkeypatch):
    monkeypatch.setattr(config, 'ASAAS_API_KEY', '$aact_prod_exemplo')
    monkeypatch.setattr(config, 'ASAAS_SANDBOX', False)

    assert asaas.esta_configurado() is True
    assert asaas.ambiente() == 'producao'
    assert asaas._base_url() == 'https://api.asaas.com/v3'
    assert asaas._headers()['access_token'] == '$aact_prod_exemplo'


def test_asaas_sem_chave_reporta_nao_configurado(monkeypatch):
    monkeypatch.setattr(config, 'ASAAS_API_KEY', '')
    assert asaas.esta_configurado() is False


def test_asaas_detecta_chave_de_producao_apontada_para_sandbox(monkeypatch):
    monkeypatch.setattr(config, 'ASAAS_API_KEY', '$aact_prod_exemplo')
    monkeypatch.setattr(config, 'ASAAS_SANDBOX', True)
    assert asaas.chave_incompativel_com_ambiente() is True


def test_asaas_nao_acusa_incompatibilidade_quando_chave_bate(monkeypatch):
    monkeypatch.setattr(config, 'ASAAS_API_KEY', '$aact_hmlg_exemplo')
    monkeypatch.setattr(config, 'ASAAS_SANDBOX', True)
    assert asaas.chave_incompativel_com_ambiente() is False


# -----------------------------------------------------------------------------
# M5 - cabecalhos de seguranca
# -----------------------------------------------------------------------------
def test_resposta_traz_cabecalhos_de_seguranca(client):
    cabecalhos = client.get('/api/clientes').headers

    assert "default-src 'self'" in cabecalhos['Content-Security-Policy']
    assert cabecalhos['X-Content-Type-Options'] == 'nosniff'
    assert cabecalhos['X-Frame-Options'] == 'DENY'


def test_csp_libera_apenas_as_origens_externas_realmente_usadas(client):
    csp = client.get('/').headers['Content-Security-Policy']

    assert 'https://viacep.com.br' in csp
    assert 'https://nominatim.openstreetmap.org' in csp
    assert "frame-ancestors 'none'" in csp


# -----------------------------------------------------------------------------
# B1 - planilha compartilhada entre exportacao e OneDrive
# -----------------------------------------------------------------------------
def test_planilha_escreve_cabecalhos_e_valores():
    import openpyxl

    buffer = planilha.construir_planilha(
        "Clientes", ["Nome", "Cidade"], ['nome', 'cidade'],
        [{'nome': 'Ana', 'cidade': 'Santos'}, {'nome': 'Bruno', 'cidade': 'Recife'}],
    )
    ws = openpyxl.load_workbook(buffer).active

    assert ws.title == "Clientes"
    assert [c.value for c in ws[1]] == ["Nome", "Cidade"]
    assert [c.value for c in ws[2]] == ["Ana", "Santos"]
    assert ws.max_row == 3


def test_planilha_tolera_registro_sem_o_campo():
    import openpyxl

    buffer = planilha.construir_planilha(
        "X", ["Nome", "Obs"], ['nome', 'observacoes'], [{'nome': 'Ana'}],
    )
    ws = openpyxl.load_workbook(buffer).active

    assert ws.cell(row=2, column=2).value in (None, '')


# -----------------------------------------------------------------------------
# M2 - Alembic resolvia alembic.ini pelo CWD e nunca rodava de fato
# -----------------------------------------------------------------------------
def test_migracoes_aplicam_a_partir_de_qualquer_diretorio(tmp_path, monkeypatch):
    """
    Roda com o CWD fora de backend/, que era exatamente o caso em que
    `Config("alembic.ini")` falhava e a aplicacao caia no fallback silencioso.
    """
    import sqlite3
    import migrations_manager

    monkeypatch.chdir(tmp_path)
    banco = tmp_path / 'migracao.db'
    monkeypatch.setattr(database, 'DB_PATH', str(banco))

    migrations_manager.aplicar_migrações()

    conexao = sqlite3.connect(banco)
    try:
        tabelas = {r[0] for r in conexao.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        assert {'clientes', 'pagamentos', 'sessao', 'historico',
                'clientes_asaas', 'entregas_agendadas'} <= tabelas
        assert conexao.execute('SELECT version_num FROM alembic_version').fetchone()
    finally:
        conexao.close()


def test_migracao_inicial_usa_tipos_validos_do_sqlalchemy():
    """
    A migracao usava `sa.Real()`, que nao existe — erro invisivel enquanto o
    Alembic nunca chegava a executar.
    """
    import re
    import sqlalchemy as sa

    caminho = os.path.join(
        os.path.dirname(__file__), '..', 'backend', 'migrations', 'versions',
        '21d8d4eb2b6f_initial_schema.py')
    with open(caminho, encoding='utf-8') as arquivo:
        origem = arquivo.read()

    desconhecidos = [t for t in set(re.findall(r'sa\.([A-Za-z_]+)\(', origem))
                     if not hasattr(sa, t)]
    assert not desconhecidos, f"Tipos inexistentes no SQLAlchemy: {desconhecidos}"


# -----------------------------------------------------------------------------
# UI - dialogos nativos substituidos e pagina de callback tematizada
# -----------------------------------------------------------------------------
def _ler_app_js():
    caminho = os.path.join(os.path.dirname(__file__), '..', 'frontend', 'js', 'app.js')
    with open(caminho, encoding='utf-8') as arquivo:
        return arquivo.read()


def test_frontend_nao_usa_dialogos_nativos():
    """
    confirm()/alert() nativos ignoram o tema e exibem o endereco do servidor
    ("127.0.0.1:5000 diz"). Devem passar por confirmarAcao().
    """
    import re

    codigo = _ler_app_js()
    sem_comentarios = re.sub(r'//.*', '', codigo)
    # O lookbehind ja descarta `window.confirm(`, mantido apenas como fallback
    # interno de confirmarAcao() para o caso do modal nao existir no DOM.
    chamadas = re.findall(r'(?<![.\w])(confirm|alert|prompt)\s*\(', sem_comentarios)
    assert chamadas == [], f"Dialogos nativos remanescentes: {chamadas}"


def test_confirmar_acao_esta_definida_e_modal_existe_no_template():
    assert 'function confirmarAcao(' in _ler_app_js()

    caminho = os.path.join(os.path.dirname(__file__), '..', 'backend', 'templates', 'index.html')
    with open(caminho, encoding='utf-8') as arquivo:
        html = arquivo.read()
    for elemento in ('id="modalConfirmar"', 'id="modalConfirmarTitulo"',
                     'id="modalConfirmarMsg"', 'id="modalConfirmarOk"',
                     'id="modalConfirmarCancelar"'):
        assert elemento in html, f"Faltando no template: {elemento}"


def test_callback_de_erro_renderiza_como_erro(client):
    """
    O template tem `{% if erro %}`, mas app.py nunca passava a variavel: toda
    tela de falha do login aparecia com o check verde de sucesso.
    """
    resposta = client.get('/callback')  # sem `code` -> erro

    assert resposta.status_code == 400
    corpo = resposta.data.decode('utf-8')
    assert 'var(--erro)' in corpo, "Tela de erro nao usa a cor de erro"
    assert 'var(--ok)' not in corpo, "Tela de erro herdou o visual de sucesso"


def test_callback_usa_o_tema_escuro_do_app(client):
    corpo = client.get('/callback').data.decode('utf-8')

    assert '#0f172a' in corpo, "Callback nao usa o fundo escuro do app"
    assert 'background:#f4f6f9' not in corpo, "Callback ainda tem o fundo claro antigo"


# -----------------------------------------------------------------------------
# Notificacoes lidas
# -----------------------------------------------------------------------------
def test_notificacao_tem_chave_estavel_e_flag_de_leitura(client):
    _criar_cliente_com_pagamento(client, '2020-01-01')

    notifs = json.loads(client.get('/api/notificacoes').data)['notificacoes']

    atrasado = next(n for n in notifs if n['tipo'] == 'pagamento_atrasado')
    assert atrasado['chave'].startswith('pagamento_atrasado:')
    assert atrasado['lida'] is False


def test_marcar_e_desmarcar_notificacao_como_lida(client):
    _criar_cliente_com_pagamento(client, '2020-01-01')
    chave = json.loads(client.get('/api/notificacoes').data)['notificacoes'][0]['chave']

    marcar = client.post('/api/notificacoes/lidas', headers={'Origin': ORIGEM_LOCAL},
                         data=json.dumps({'chaves': [chave]}), content_type='application/json')
    assert marcar.status_code == 200
    dados = json.loads(client.get('/api/notificacoes').data)
    assert dados['nao_lidas'] == 0
    assert all(n['lida'] for n in dados['notificacoes'])

    client.delete('/api/notificacoes/lidas', headers={'Origin': ORIGEM_LOCAL},
                  data=json.dumps({'chaves': [chave]}), content_type='application/json')
    assert json.loads(client.get('/api/notificacoes').data)['nao_lidas'] == 1


def test_marcar_como_lida_e_idempotente(client):
    _criar_cliente_com_pagamento(client, '2020-01-01')
    chave = json.loads(client.get('/api/notificacoes').data)['notificacoes'][0]['chave']
    corpo = json.dumps({'chaves': [chave]})

    for _ in range(3):
        client.post('/api/notificacoes/lidas', headers={'Origin': ORIGEM_LOCAL},
                    data=corpo, content_type='application/json')

    assert json.loads(client.get('/api/notificacoes').data)['nao_lidas'] == 0


def test_marcar_todas_como_lidas(client):
    _criar_cliente_com_pagamento(client, '2020-01-01')
    database.agendar_entrega(1, 'Cliente Teste', '2020-01-01', '', 'Atrasada')
    assert json.loads(client.get('/api/notificacoes').data)['nao_lidas'] >= 2

    client.post('/api/notificacoes/lidas', headers={'Origin': ORIGEM_LOCAL},
                data=json.dumps({'todas': True}), content_type='application/json')

    assert json.loads(client.get('/api/notificacoes').data)['nao_lidas'] == 0


def test_nao_lidas_aparecem_antes_das_lidas(client):
    _criar_cliente_com_pagamento(client, '2020-01-01')
    database.agendar_entrega(1, 'Cliente Teste', '2020-01-01', '', 'Atrasada')
    notifs = json.loads(client.get('/api/notificacoes').data)['notificacoes']
    client.post('/api/notificacoes/lidas', headers={'Origin': ORIGEM_LOCAL},
                data=json.dumps({'chaves': [notifs[0]['chave']]}), content_type='application/json')

    ordem = [n['lida'] for n in json.loads(client.get('/api/notificacoes').data)['notificacoes']]

    assert ordem == sorted(ordem), f"Lidas deveriam vir por ultimo: {ordem}"


def test_chaves_invalidas_sao_ignoradas(client):
    resposta = client.post('/api/notificacoes/lidas', headers={'Origin': ORIGEM_LOCAL},
                           data=json.dumps({'chaves': ['', '   ']}), content_type='application/json')
    assert resposta.status_code == 200
    assert json.loads(resposta.data)['quantidade'] == 0


# -----------------------------------------------------------------------------
# Dashboard financeiro
# -----------------------------------------------------------------------------
def _receber(cliente_id, valor, data_pagamento, vencimento=None):
    pagamento_id = database.salvar_pagamento(
        cliente_id, 'Cliente Teste', valor, 'Locacao', vencimento or data_pagamento[:10])
    with database.conectar() as conexao:
        conexao.execute("UPDATE pagamentos SET status='Recebido', data_pagamento=? WHERE id=?",
                        (data_pagamento, pagamento_id))
    return pagamento_id


def test_faturamento_soma_os_dois_formatos_de_data_pagamento(client):
    """Confirmacao manual grava 'AAAA-MM-DD'; o webhook grava com hora."""
    from datetime import date
    hoje = date.today()
    cliente_id = _criar_cliente_com_pagamento(client, '2030-01-01')
    _receber(cliente_id, 100.00, hoje.strftime('%Y-%m-%d'))
    _receber(cliente_id, 250.00, hoje.strftime('%Y-%m-%d 14:22:10'))

    fin = database.obter_metricas_financeiras()

    assert fin['faturamento_mes'] == 350.00
    assert fin['qtd_recebimentos_mes'] == 2
    assert fin['ticket_medio_mes'] == 175.00


def test_variacao_percentual_compara_com_mes_anterior(client):
    from datetime import date
    hoje = date.today()
    mes_passado = (hoje.replace(day=1) - timedelta(days=1))
    cliente_id = _criar_cliente_com_pagamento(client, '2030-01-01')
    _receber(cliente_id, 200.00, mes_passado.strftime('%Y-%m-%d'))
    _receber(cliente_id, 300.00, hoje.strftime('%Y-%m-%d'))

    fin = database.obter_metricas_financeiras()

    assert fin['faturamento_mes_anterior'] == 200.00
    assert fin['variacao_percentual'] == 50.0


def test_variacao_e_nula_sem_base_de_comparacao(client):
    """Sem receita no mes anterior nao existe variacao: `None`, nao zero."""
    fin = database.obter_metricas_financeiras()
    assert fin['faturamento_mes'] == 0
    assert fin['variacao_percentual'] is None


def test_serie_mensal_preenche_meses_sem_receita(client):
    fin = database.obter_metricas_financeiras(meses_historico=6)

    serie = fin['serie_mensal']
    assert len(serie) == 6, "A serie deve ter um ponto por mes, mesmo sem receita"
    assert all('mes' in p and 'total' in p for p in serie)
    meses = [p['mes'] for p in serie]
    assert meses == sorted(meses), "A serie deve estar em ordem cronologica"


def test_em_atraso_conta_apenas_vencidos_nao_pagos(client):
    cliente_id = _criar_cliente_com_pagamento(client, '2020-01-01')   # vencido
    database.salvar_pagamento(cliente_id, 'Cliente Teste', 999.00, 'Futuro', '2030-01-01')

    fin = database.obter_metricas_financeiras()

    assert fin['qtd_em_atraso'] == 1
    assert fin['em_atraso'] == 250.00      # so o vencido
    assert fin['a_receber'] == 1249.00     # ambos os pendentes


def test_endpoint_de_dashboard_expoe_o_financeiro(client):
    resposta = client.get('/api/dashboard/dados')

    assert resposta.status_code == 200
    dados = json.loads(resposta.data)
    assert 'financeiro' in dados
    for campo in ('faturamento_mes', 'faturamento_mes_anterior', 'variacao_percentual',
                  'a_receber', 'em_atraso', 'ticket_medio_mes', 'serie_mensal'):
        assert campo in dados['financeiro'], f"Falta {campo} no bloco financeiro"


def test_dashboard_nao_exibe_mais_o_texto_atualizado():
    caminho = os.path.join(os.path.dirname(__file__), '..', 'backend', 'templates', 'index.html')
    with open(caminho, encoding='utf-8') as arquivo:
        html = arquivo.read()

    assert 'metricAtualizado' not in html
    assert 'Atualizado:' not in html
    # os canvases precisam existir, senao o codigo dos graficos nunca roda
    for canvas in ('chartReceitaMensal', 'chartEntregaRetirada', 'chartCidades', 'chartTimeline'):
        assert f'id="{canvas}"' in html, f"Canvas ausente: {canvas}"


def test_relatorio_xlsx_e_gerado_pelo_endpoint(client):
    _criar_cliente_com_pagamento(client, '2030-01-01')

    resposta = client.get('/api/relatorios/exportar?formato=xlsx')

    assert resposta.status_code == 200
    assert resposta.data[:2] == b'PK'  # xlsx e um zip
