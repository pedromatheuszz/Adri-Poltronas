"""
Testes de regressão para os defeitos da segunda auditoria técnica.

Cada bloco referencia o item do relatório que o originou. Todos falham
na versão anterior do código.
"""
import io
import os
import sys
import json
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

import database  # noqa: E402
import app as app_module  # noqa: E402

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


def _criar_cliente(client, nome="Cliente Teste"):
    client.post('/api/clientes', headers={'Origin': ORIGEM_LOCAL},
        data=json.dumps({
            "nome": nome, "cep": "12345-678", "rua": "Rua Teste",
            "bairro": "Centro", "cidade": "São Paulo", "entrega_retirada": "Entrega",
        }), content_type='application/json')
    return json.loads(client.get('/api/clientes').data)[0]['id']


def _post_pagamento(client, **campos):
    corpo = {
        "cliente_id": campos.pop("cliente_id"),
        "cliente_nome": "Cliente Teste",
        "valor": 250.00,
        "descricao": "Poltrona",
        "data_vencimento": "2020-01-10",
        "tipo_pagamento": "Dinheiro",
    }
    corpo.update(campos)
    return client.post('/api/pagamentos', headers={'Origin': ORIGEM_LOCAL},
        data=json.dumps(corpo), content_type='application/json')


# -----------------------------------------------------------------------------
# Item 1 - POST /api/pagamentos descartava `status` e `data_pagamento`, e o
# recebimento registrado pelo modal virava "Pendente" -- vencido, portanto
# contabilizado como ATRASADO no mesmo instante em que era recebido.
# -----------------------------------------------------------------------------










# -----------------------------------------------------------------------------
# Item 2 - PUT /api/pagamentos/<id> injetava status='Pendente' sempre que o
# corpo nao trazia o campo. Editar a descricao de uma cobranca ja recebida
# revertia o recebimento e apagava a receita do faturamento.
# -----------------------------------------------------------------------------
def _pagamento_recebido(client):
    cliente_id = _criar_cliente(client)
    resposta = _post_pagamento(client, cliente_id=cliente_id,
        status="Recebido", data_pagamento="2020-01-10")
    return cliente_id, json.loads(resposta.data)['id']


def _put_pagamento(client, pagamento_id, cliente_id, **campos):
    corpo = {
        "cliente_id": cliente_id,
        "cliente_nome": "Cliente Teste",
        "valor": 250.00,
        "descricao": "Poltrona",
        "data_vencimento": "2020-01-10",
        "tipo_pagamento": "Dinheiro",
    }
    corpo.update(campos)
    return client.put(f'/api/pagamentos/{pagamento_id}', headers={'Origin': ORIGEM_LOCAL},
        data=json.dumps(corpo), content_type='application/json')












# -----------------------------------------------------------------------------
# Regressoes introduzidas na camada de seguranca adicionada durante a auditoria
# -----------------------------------------------------------------------------
def test_markup_nao_tem_handler_inline(client):
    """
    Os 36 `onclick=` do template viraram comandos declarativos (`data-comando`).

    O teste guarda a condicao que permite a CSP recusar script inline: basta um
    `onclick=` voltar ao markup para a interface quebrar em silencio -- o
    navegador bloqueia o handler sem aviso visivel na tela.
    """
    template = os.path.join(os.path.dirname(__file__), '..', 'backend', 'templates', 'index.html')
    with open(template, encoding='utf-8') as f:
        markup = f.read()

    assert 'onclick=' not in markup, (
        "handler inline de volta no template: ou ele vira data-acao, ou a CSP "
        "precisa liberar 'unsafe-inline' de novo -- e a liberacao vale para "
        "todo script inline da pagina, nao so para este"
    )
    assert 'data-comando=' in markup, "os comandos declarativos sumiram do template"


def test_csp_recusa_script_inline(client):
    """
    Enquanto havia `onclick=` no markup, `script-src` precisava de
    'unsafe-inline'. Essa liberacao nao e seletiva: vale para TODO script
    inline da pagina, inclusive um que venha a ser injetado por um campo de
    cadastro mal escapado.
    """
    import re as _re
    csp = client.get('/').headers['Content-Security-Policy']
    script_src = _re.search(r'script-src([^;]*)', csp).group(1)

    assert "'unsafe-inline'" not in script_src
    assert "'self'" in script_src

    # `style-src` mantem a liberacao de proposito: Leaflet e Chart.js
    # posicionam elementos escrevendo no atributo `style` em tempo de execucao.
    # Estilo injetado permite defacement, nao execucao de codigo.
    style_src = _re.search(r'style-src([^;]*)', csp).group(1)
    assert "'unsafe-inline'" in style_src


def test_limpar_csrf_cache_preserva_tokens_vivos():
    """Reconstruir o cache lendo do dicionario ja esvaziado levantava KeyError."""
    import app as app_module_local
    cache = app_module_local._csrf_token_cache
    cache.clear()
    cache['vivo'] = {'token': 'a', 'gerado_em': __import__('time').time()}
    cache['expirado'] = {'token': 'b', 'gerado_em': 0}

    app_module_local.limpar_csrf_cache()

    assert 'vivo' in cache
    assert 'expirado' not in cache
    cache.clear()


def test_validar_sessao_segura_nao_levanta_nameerror():
    """`_SESSION_TIMEOUT` era usado sem existir; a constante e `_SESSAO_TIMEOUT`."""
    import security
    sessao_id = security.criar_sessao_segura("conta@exemplo.com", "token-qualquer")
    assert security.validar_sessao_segura(sessao_id) is not None
    security.destruir_sessao_segura(sessao_id)


# -----------------------------------------------------------------------------
# Item 3 - DELETE /api/pagamentos/<id> chamava o Asaas ANTES de checar se a
# cobranca era cancelavel. Num pagamento ja recebido a cobranca era cancelada
# no gateway e o registro local permanecia intacto: divergencia permanente.
# -----------------------------------------------------------------------------
@pytest.fixture
def asaas_espiao(monkeypatch):
    """Registra as chamadas ao Asaas sem tocar na rede."""
    import asaas
    chamadas = []

    def _cancelar(asaas_payment_id):
        chamadas.append(asaas_payment_id)
        return dict(_cancelar.resposta)

    _cancelar.resposta = {"deleted": True}
    monkeypatch.setattr(asaas, 'esta_configurado', lambda: True)
    monkeypatch.setattr(asaas, 'cancelar_pagamento', _cancelar)
    return chamadas, _cancelar








# -----------------------------------------------------------------------------
# Item 7 - o app instalado nao tinha como receber segredos. O setup.iss instala
# em Program Files sem nenhum .env, e load_dotenv() resolve a partir do CWD.
# ASAAS_API_KEY, ASAAS_WEBHOOK_TOKEN e GEMINI_API_KEY nasciam vazias no produto
# entregue -- pagamentos online e webhook desligados de fabrica.
# -----------------------------------------------------------------------------
def test_env_do_usuario_fica_junto_do_banco_e_dos_logs(tmp_path, monkeypatch):
    import config
    monkeypatch.setenv('APPDATA', str(tmp_path))
    caminho = config.caminho_env_do_usuario()
    assert caminho == os.path.join(str(tmp_path), 'AdriPoltronas', '.env')


def test_modelo_de_env_e_criado_na_primeira_execucao(tmp_path, monkeypatch):
    import config
    monkeypatch.setenv('APPDATA', str(tmp_path))
    caminho = config.garantir_modelo_env()

    assert caminho and os.path.exists(caminho)
    conteudo = open(caminho, encoding='utf-8').read()
    for chave in ('MP_ACCESS_TOKEN', 'GEMINI_API_KEY', 'ADRI_FLASK_SECRET'):
        assert chave in conteudo


def test_modelo_de_env_nao_sobrescreve_arquivo_existente(tmp_path, monkeypatch):
    import config
    monkeypatch.setenv('APPDATA', str(tmp_path))
    caminho = os.path.join(str(tmp_path), 'AdriPoltronas', '.env')
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    with open(caminho, 'w', encoding='utf-8') as f:
        f.write('ASAAS_API_KEY=chave_real_do_usuario\n')

    config.garantir_modelo_env()

    assert 'chave_real_do_usuario' in open(caminho, encoding='utf-8').read()


def test_valores_do_env_do_usuario_sao_carregados(tmp_path, monkeypatch):
    import config
    monkeypatch.setenv('APPDATA', str(tmp_path))
    caminho = os.path.join(str(tmp_path), 'AdriPoltronas', '.env')
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    with open(caminho, 'w', encoding='utf-8') as f:
        f.write('ADRI_VALOR_DE_TESTE=funcionou\n')
    monkeypatch.delenv('ADRI_VALOR_DE_TESTE', raising=False)

    config.carregar_configuracao()

    assert os.environ.get('ADRI_VALOR_DE_TESTE') == 'funcionou'


# -----------------------------------------------------------------------------
# Itens 4 e 5 - Service Worker
# -----------------------------------------------------------------------------
def _ler_sw_js():
    caminho = os.path.join(os.path.dirname(__file__), '..', 'frontend', 'sw.js')
    with open(caminho, encoding='utf-8') as arquivo:
        return arquivo.read()


def test_service_worker_nao_cacheia_respostas_de_api():
    """
    Item 4: toda resposta GET sob /api/ ia para o Cache Storage, incluindo
    /api/clientes/backup/sqlite (o banco inteiro) e /api/clientes (nome, CEP e
    endereco de todos os clientes). O cache fica em disco, sem cifragem, e o
    handler de activate nunca expurgava CACHE_API.
    """
    codigo = _ler_sw_js()
    assert 'CACHE_API' not in codigo, "ainda existe um cache dedicado a respostas de API"
    assert 'networkFirstStrategy' not in codigo or 'cache.put' not in codigo.split(
        'async function networkFirstStrategy')[1].split('async function')[0], \
        "a estrategia de API ainda grava a resposta em cache"


def test_precache_nao_depende_de_cdn_externo():
    """
    Item 5: cache.addAll() e atomico. Com URLs de CDN na lista, abrir o app
    uma primeira vez sem internet fazia o install inteiro falhar -- e o PWA
    ficava sem nenhum asset cacheado.
    """
    import re
    codigo = _ler_sw_js()
    bloco = re.search(r'PRECACHE_ASSETS\s*=\s*\[(.*?)\]', codigo, re.DOTALL).group(1)
    assert 'http' not in bloco, "o precache atomico ainda inclui URLs externas"


# -----------------------------------------------------------------------------
# Item 6 - o backend roda em 127.0.0.1, mas todo o CRUD decidia entre servidor
# e fila offline por `navigator.onLine`, que mede a internet. Cair o WiFi jogava
# o app na fila offline com o servidor local respondendo normalmente.
# -----------------------------------------------------------------------------
def _ler_app_js():
    caminho = os.path.join(os.path.dirname(__file__), '..', 'frontend', 'js', 'app.js')
    with open(caminho, encoding='utf-8') as arquivo:
        return arquivo.read()


def test_crud_nao_decide_offline_por_navigator_online():
    import re as _re
    # Comentarios sao removidos: o proprio comentario que explica a correcao
    # cita navigator.onLine. Mesma abordagem de test_regressoes.py.
    codigo = _re.sub(r'//.*', '', _ler_app_js())
    assert 'navigator.onLine' not in codigo, (
        "app.js ainda usa navigator.onLine para decidir se fala com o backend local"
    )


def test_existe_helper_de_disponibilidade_do_backend():
    codigo = _ler_app_js()
    assert 'async function tentarBackend(' in codigo
    # A fila offline so pode ser acionada pelo sinal do helper.
    assert codigo.count('semBackend') >= 4


# -----------------------------------------------------------------------------
# Item 14 - a fila de sincronizacao nao tinha limite de tentativas nem guarda
# de concorrencia. Um item invalido (400) era reenviado para sempre a cada
# reconexao, e o evento `online` somado a uma chamada manual podia rodar duas
# sincronizacoes em paralelo, duplicando POSTs de criacao.
# -----------------------------------------------------------------------------
def _ler_offline_js():
    caminho = os.path.join(os.path.dirname(__file__), '..', 'frontend', 'js', 'offline.js')
    with open(caminho, encoding='utf-8') as arquivo:
        return arquivo.read()


def test_sync_tem_guarda_de_concorrencia():
    codigo = _ler_offline_js()
    assert 'sincronizacaoEmCurso' in codigo
    assert 'finally' in codigo.split('async function syncPendingActions')[1][:2000]


def test_sync_descarta_item_permanentemente_invalido():
    """Um 4xx nao muda de resultado por reenvio: o item precisa sair da fila."""
    corpo = _ler_offline_js().split('async function syncPendingActions')[1]
    assert 'status >= 400' in corpo and 'status < 500' in corpo


def test_sync_limita_tentativas():
    codigo = _ler_offline_js()
    assert 'MAX_TENTATIVAS_SYNC' in codigo
    assert 'tentativas' in codigo


def test_falha_de_rede_nao_consome_tentativas():
    """Backend fora do ar nao e culpa do payload; interrompe sem penalizar."""
    corpo = _ler_offline_js().split('async function syncPendingActions')[1]
    assert 'break' in corpo


# -----------------------------------------------------------------------------
# Item 15 - `cacheClientes` so fazia put(). Um cliente criado offline (id
# negativo) permanecia no IndexedDB depois de sincronizado com id real -- e
# aparecia duplicado -- e clientes excluidos no servidor nunca sumiam do cache.
# -----------------------------------------------------------------------------
def test_existe_sincronizacao_autoritativa_do_cache():
    codigo = _ler_offline_js()
    assert 'async function sincronizarCache(' in codigo
    corpo = codigo.split('async function sincronizarCache(')[1].split('async function')[0]
    assert 'store.clear()' in corpo, "o cache nao e podado antes de receber a lista do servidor"


def test_sincronizacao_respeita_fila_pendente():
    """Com pendencias na fila o servidor ainda nao e a verdade completa."""
    codigo = _ler_offline_js()
    corpo = codigo.split('async function sincronizarCache(')[1].split('async function')[0]
    assert 'getPendingCount' in corpo


def test_sincronizar_cache_e_exportado_e_usado_pelo_app():
    assert 'sincronizarCache: sincronizarCache' in _ler_offline_js()
    assert 'OfflineManager.sincronizarCache(' in _ler_app_js()


# -----------------------------------------------------------------------------
# Item 9 - urllib.parse.quote usa safe='/' por padrao, entao barras do nome
# informado pelo usuario passavam intactas para a URL do Graph:
# '../../Documentos/x' virava 'root:/../../Documentos/x.xlsx:/content'.
# -----------------------------------------------------------------------------




# -----------------------------------------------------------------------------
# Item 10 - int() sem guarda derrubava o endpoint com 500 e stack trace.
# -----------------------------------------------------------------------------






# -----------------------------------------------------------------------------
# Item 11 - PUT em cliente inexistente respondia 200 "Atualizado" e ainda
# gravava uma linha fantasma de ATUALIZACAO no historico.
# -----------------------------------------------------------------------------
def _corpo_cliente(**campos):
    corpo = {
        "nome": "Outro Nome", "cep": "12345-678", "rua": "Rua Nova",
        "bairro": "Centro", "cidade": "São Paulo", "entrega_retirada": "Entrega",
    }
    corpo.update(campos)
    return corpo


def test_put_em_cliente_inexistente_retorna_404(client):
    resposta = client.put('/api/clientes/999999', headers={'Origin': ORIGEM_LOCAL},
        data=json.dumps(_corpo_cliente()), content_type='application/json')
    assert resposta.status_code == 404


def test_put_em_cliente_inexistente_nao_grava_historico(client):
    client.put('/api/clientes/999999', headers={'Origin': ORIGEM_LOCAL},
        data=json.dumps(_corpo_cliente()), content_type='application/json')
    with database.conectar() as conexao:
        total = conexao.execute(
            "SELECT COUNT(*) FROM historico WHERE cliente_id=999999").fetchone()[0]
    assert total == 0


def test_put_em_cliente_existente_continua_funcionando(client):
    cliente_id = _criar_cliente(client)
    resposta = client.put(f'/api/clientes/{cliente_id}', headers={'Origin': ORIGEM_LOCAL},
        data=json.dumps(_corpo_cliente(nome="Nome Atualizado")), content_type='application/json')
    assert resposta.status_code == 200
    assert database.obter_cliente_por_id(cliente_id)['nome'] == 'Nome Atualizado'


# -----------------------------------------------------------------------------
# Item 12 - POST /api/entregas aceitava cliente_id inexistente e data em
# formato livre. `date(data_entrega)` no SQL das notificacoes devolvia NULL
# silenciosamente e a entrega sumia dos alertas.
# -----------------------------------------------------------------------------
def _post_entrega(client, **campos):
    corpo = {"cliente_id": 1, "data_entrega": "2026-09-01"}
    corpo.update(campos)
    return client.post('/api/entregas', headers={'Origin': ORIGEM_LOCAL},
        data=json.dumps(corpo), content_type='application/json')


def test_entrega_com_data_em_formato_livre_e_recusada(client):
    cliente_id = _criar_cliente(client)
    resposta = _post_entrega(client, cliente_id=cliente_id, data_entrega="amanha de tarde")
    assert resposta.status_code == 400


def test_entrega_com_cliente_inexistente_e_recusada(client):
    resposta = _post_entrega(client, cliente_id=999999)
    assert resposta.status_code == 404


def test_entrega_com_cliente_id_nao_numerico_e_recusada(client):
    resposta = _post_entrega(client, cliente_id="nao-existe")
    assert resposta.status_code == 400


def test_entrega_com_hora_invalida_e_recusada(client):
    cliente_id = _criar_cliente(client)
    resposta = _post_entrega(client, cliente_id=cliente_id, hora_entrega="25:99")
    assert resposta.status_code == 400


def test_entrega_valida_e_aceita(client):
    cliente_id = _criar_cliente(client)
    resposta = _post_entrega(client, cliente_id=cliente_id, hora_entrega="14:30")
    assert resposta.status_code == 201
    entregas = database.listar_entregas_agendadas()
    assert len(entregas) == 1
    assert entregas[0]['cliente_nome'] == 'Cliente Teste'


# -----------------------------------------------------------------------------
# Item 13 - a importacao nao tinha limite de tamanho de corpo, nem teto de
# linhas, e entregava o arquivo direto ao openpyxl (zip bomb).
# -----------------------------------------------------------------------------
def _upload(client, nome, conteudo, content_type='text/csv'):
    dados = {'arquivo': (io.BytesIO(conteudo), nome, content_type)}
    return client.post('/api/clientes/importar', headers={'Origin': ORIGEM_LOCAL},
        data=dados, content_type='multipart/form-data')


def test_app_tem_limite_de_corpo_da_requisicao():
    import app as app_module_local
    limite = app_module_local.app.config.get('MAX_CONTENT_LENGTH')
    assert limite is not None and 0 < limite <= 32 * 1024 * 1024


def test_upload_acima_do_limite_e_recusado(client):
    import app as app_module_local
    excesso = (app_module_local.app.config['MAX_CONTENT_LENGTH'] or 0) + 1024
    resposta = _upload(client, 'grande.csv', b'a' * excesso)
    assert resposta.status_code == 413


def test_upload_de_extensao_nao_permitida_e_recusado(client):
    resposta = _upload(client, 'payload.exe', b'MZ\x90\x00', 'application/octet-stream')
    assert resposta.status_code == 400


def test_upload_vazio_e_recusado(client):
    resposta = _upload(client, 'vazio.csv', b'')
    assert resposta.status_code == 400


def test_importacao_tem_teto_de_linhas(client):
    from blueprints.clientes import MAX_LINHAS_IMPORTACAO
    assert 0 < MAX_LINHAS_IMPORTACAO <= 50000

    linhas = [b'nome,cep,rua,bairro,cidade,entrega_retirada']
    for i in range(MAX_LINHAS_IMPORTACAO + 5):
        linhas.append(f'Cliente {i},12345-678,Rua A,Centro,Sao Paulo,Entrega'.encode())
    resposta = _upload(client, 'muitos.csv', b'\n'.join(linhas))

    assert resposta.status_code == 400
    assert 'linhas' in json.loads(resposta.data)['erro'].lower()


def test_importacao_valida_continua_funcionando(client):
    csv = (b'nome,cep,rua,bairro,cidade,entrega_retirada\n'
           b'Maria Souza,12345-678,Rua A,Centro,Sao Paulo,Entrega\n')
    resposta = _upload(client, 'ok.csv', csv)
    assert resposta.status_code == 200
    assert json.loads(resposta.data)['sucessos'] == 1


# -----------------------------------------------------------------------------
# Item 17 - a consulta de clientes inativos nao tinha LIMIT. Numa base madura o
# painel de notificacoes virava milhares de itens, remontados a cada
# atualizacao (e o endpoint devolve todos de uma vez).
# -----------------------------------------------------------------------------
def _criar_clientes_inativos(quantidade):
    with database.conectar() as conexao:
        for i in range(quantidade):
            conexao.execute(
                "INSERT INTO clientes (nome, cep, rua, bairro, cidade, entrega_retirada, "
                "criado_em, atualizado_em) VALUES (?, ?, ?, ?, ?, ?, "
                "datetime('now', '-400 days'), datetime('now', '-400 days'))",
                (f"Inativo {i}", "12345-678", "Rua A", "Centro", "Sao Paulo", "Entrega"),
            )


def test_notificacoes_de_inativos_sao_limitadas(client):
    from database import MAX_NOTIFICACOES_POR_TIPO
    _criar_clientes_inativos(MAX_NOTIFICACOES_POR_TIPO + 25)

    inativos = [n for n in database.obter_notificacoes() if n['tipo'] == 'cliente_inativo']
    assert len(inativos) == MAX_NOTIFICACOES_POR_TIPO


def test_endpoint_de_notificacoes_nao_devolve_lista_ilimitada(client):
    from database import MAX_NOTIFICACOES_POR_TIPO
    _criar_clientes_inativos(MAX_NOTIFICACOES_POR_TIPO + 25)

    dados = json.loads(client.get('/api/notificacoes').data)
    assert dados['total'] <= MAX_NOTIFICACOES_POR_TIPO * 6


def test_notificacoes_continuam_funcionando_abaixo_do_teto(client):
    _criar_clientes_inativos(3)
    inativos = [n for n in database.obter_notificacoes() if n['tipo'] == 'cliente_inativo']
    assert len(inativos) == 3


# -----------------------------------------------------------------------------
# Item 8 - Leaflet e Chart.js vinham de CDN sem `integrity`. Uma resposta
# adulterada executava JS num app que guarda token OAuth com Files.ReadWrite
# no OneDrive do usuario e a base inteira de clientes.
# -----------------------------------------------------------------------------
def _ler_index_html():
    caminho = os.path.join(os.path.dirname(__file__), '..', 'backend', 'templates', 'index.html')
    with open(caminho, encoding='utf-8') as arquivo:
        return arquivo.read()


def test_todo_recurso_externo_tem_integrity_e_crossorigin():
    import re as _re
    html = _ler_index_html()
    tags = _re.findall(r'<(?:script|link)[^>]*\bhttps://[^>]*>', html)
    assert tags, "nenhum recurso externo encontrado no template"
    for tag in tags:
        # fonts.googleapis.com serve CSS gerado por user-agent: o conteudo
        # varia legitimamente e nao admite hash fixo.
        if 'fonts.googleapis.com' in tag or 'fonts.gstatic.com' in tag:
            continue
        assert 'integrity="sha384-' in tag, f"sem SRI: {tag[:110]}"
        assert 'crossorigin=' in tag, f"sem crossorigin (SRI exige): {tag[:110]}"


# -----------------------------------------------------------------------------
# Item 16 - a Nominatim exige 1 req/s e o mapa geocodifica em serie. Com cache
# so em memoria, tudo era refeito a cada reinicio (~4 min para 200 clientes), e
# trocar de aba no meio nao interrompia o laco.
# -----------------------------------------------------------------------------
def test_geocache_e_persistido_entre_sessoes():
    codigo = _ler_app_js()
    assert 'CHAVE_GEOCACHE' in codigo
    assert 'localStorage.getItem(CHAVE_GEOCACHE' in codigo
    assert 'localStorage.setItem(CHAVE_GEOCACHE' in codigo


def test_leitura_do_geocache_tolera_storage_indisponivel():
    """Janela anonima ou storage bloqueado nao pode derrubar o mapa."""
    corpo = _ler_app_js().split('function carregarGeocache()')[1].split('function guardarGeocache')[0]
    assert 'try' in corpo and 'catch' in corpo


def test_carregamento_obsoleto_do_mapa_e_abortado():
    codigo = _ler_app_js()
    assert '_geracaoMapa' in codigo
    corpo = codigo.split('async function carregarMapaClientes')[1]
    assert corpo.count('geracao !== _geracaoMapa') >= 2


# -----------------------------------------------------------------------------
# Itens 19/20 - sinks de atributo montados por concatenacao no frontend.
# -----------------------------------------------------------------------------


# -----------------------------------------------------------------------------
# Item 23 - literais de string em SQL com aspas duplas. Funciona no SQLite so
# porque nao existe coluna com esse nome; e uma extensao de compatibilidade que
# pode ser desligada (e o e, em builds com SQLITE_DQS=0).
# -----------------------------------------------------------------------------




# -----------------------------------------------------------------------------
# Item 25 - marcar_notificacoes_lidas devolvia len(chaves), e nao quantas foram
# de fato inseridas: o INSERT OR IGNORE pode ignorar todas.
# -----------------------------------------------------------------------------
def test_marcar_lidas_devolve_quantidade_real(client):
    assert database.marcar_notificacoes_lidas(['a:1', 'b:2']) == 2
    # Repetir as mesmas chaves nao marca nada de novo.
    assert database.marcar_notificacoes_lidas(['a:1', 'b:2']) == 0
    assert database.marcar_notificacoes_lidas(['a:1', 'c:3']) == 1


def test_marcar_lidas_ignora_chaves_vazias(client):
    assert database.marcar_notificacoes_lidas(['', '  ', None]) == 0


# -----------------------------------------------------------------------------
# Item 22 - bloco de comentario duplicado no service worker.
# -----------------------------------------------------------------------------
def test_sw_nao_tem_cabecalho_duplicado():
    assert _ler_sw_js().count('// Push Notifications (futuro)') == 1


# -----------------------------------------------------------------------------
# Item 24 - o instalador ainda apontava para example.com nos campos de suporte
# e atualizacao exibidos no Painel de Controle do Windows.
#
# O instalador Inno (setup.iss) saiu junto com o WebView: quem gera o setup
# agora e o electron-builder, configurado em package.json. O risco e o mesmo --
# um endereco de exemplo vira link de suporte no Painel de Controle.
# -----------------------------------------------------------------------------
def test_instalador_nao_referencia_example_com():
    import json
    caminho = os.path.join(os.path.dirname(__file__), '..', 'package.json')
    with open(caminho, encoding='utf-8') as arquivo:
        manifesto = json.load(arquivo)
    assert 'example.com' not in json.dumps(manifesto)
    # O antigo .iss nao pode voltar sem que alguem revise estes campos.
    assert not os.path.exists(os.path.join(os.path.dirname(__file__), '..', 'setup.iss'))


# -----------------------------------------------------------------------------
# Item 26 - endereco completo dos clientes era enviado a ViaCEP e Nominatim sem
# nenhum aviso ao operador.
# -----------------------------------------------------------------------------
def test_mapa_avisa_sobre_envio_a_servicos_externos():
    html = _ler_index_html()
    assert 'aviso-dados-externos' in html
    assert 'ViaCEP' in html and 'Nominatim' in html


def test_estilo_do_aviso_existe():
    caminho = os.path.join(os.path.dirname(__file__), '..', 'frontend', 'css', 'style.css')
    with open(caminho, encoding='utf-8') as arquivo:
        assert '.aviso-dados-externos' in arquivo.read()


# -----------------------------------------------------------------------------
# O app real importa `backend.database`; a suite importa `database`. A extracao
# de notificacoes_db criou um ciclo que so quebrava no primeiro caminho: o
# mesmo arquivo era carregado duas vezes sob nomes diferentes e estourava
# ImportError no meio da inicializacao. Verde na suite, app morto no boot.
# -----------------------------------------------------------------------------
def test_app_importa_pelo_caminho_de_pacote_do_main():
    import subprocess
    raiz = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    codigo = (
        "import sys, os;"
        f"sys.path.insert(0, os.path.join({raiz!r}, 'backend'));"
        f"sys.path.insert(0, {raiz!r});"
        "from backend import database;"
        "from backend.app import app;"
        "print(len(list(app.url_map.iter_rules())))"
    )
    resultado = subprocess.run([sys.executable, '-c', codigo],
                               capture_output=True, text=True, cwd=raiz, timeout=120)
    assert resultado.returncode == 0, resultado.stderr[-2000:]
    assert int(resultado.stdout.strip().splitlines()[-1]) > 0


def test_modulo_de_notificacoes_nao_importa_database():
    """A ausencia dessa importacao e o que impede o ciclo de voltar."""
    caminho = os.path.join(os.path.dirname(__file__), '..', 'backend', 'notificacoes_db.py')
    with open(caminho, encoding='utf-8') as arquivo:
        codigo = arquivo.read()
    corpo = codigo.split('"""', 2)[-1]  # descarta o docstring do modulo
    assert 'import database' not in corpo


# -----------------------------------------------------------------------------
# Mapa quebrado: o service worker interceptava requisicoes de outra origem
# (tiles do OpenStreetMap, icones do Leaflet) e as reemitia por `fetch()`. No
# WebView2 que embalava o app ate a migracao para o Electron esse fetch falhava,
# staleWhileRevalidate caia no catch e resolvia para `undefined`, e
# respondWith(undefined) vira erro de rede. Mapa cinza, marcadores quebrados, e
# nenhuma violacao de CSP no console. Confirmado empiricamente: sem SW o tile
# carregava; com SW, falhava. A regra continua valendo -- resposta de terceiro
# e opaca e nao se cacheia.
# -----------------------------------------------------------------------------
def test_sw_nao_intercepta_outra_origem():
    import re as _re
    codigo = _ler_sw_js()
    corpo = codigo.split("addEventListener('fetch'")[1].split('async function')[0]
    # Comentarios fora: o proprio comentario que explica a correcao cita
    # respondWith, e falsearia a checagem de ordem abaixo.
    corpo = _re.sub(r'//.*', '', corpo)

    assert "url.origin !== self.location.origin" in corpo, (
        "o handler de fetch ainda intercepta requisicoes de outra origem"
    )
    # A guarda precisa vir ANTES de qualquer respondWith, senao nao protege.
    assert corpo.index('url.origin !== self.location.origin') < corpo.index('respondWith')


def test_stale_while_revalidate_nunca_resolve_para_undefined():
    corpo = _ler_sw_js().split('async function staleWhileRevalidate')[1]
    corpo = corpo.split('\n// ===')[0]
    assert 'throw erro' in corpo, (
        "sem cache e sem rede a estrategia precisa propagar o erro; "
        "devolver undefined faz respondWith abortar a requisicao de forma opaca"
    )


def test_versao_do_cache_foi_incrementada():
    """Sem bump, o estado quebrado sobrevive nas maquinas que ja rodaram."""
    import re as _re
    versao = _re.search(r"CACHE_NAME = 'adri-poltronas-v(\d+)'", _ler_sw_js())
    assert versao and int(versao.group(1)) >= 6


# -----------------------------------------------------------------------------
# Aparencia do mapa: base escura no tema do app, marcadores como ponto-sinal.
# -----------------------------------------------------------------------------
def _ler_style_css():
    caminho = os.path.join(os.path.dirname(__file__), '..', 'frontend', 'css', 'style.css')
    with open(caminho, encoding='utf-8') as arquivo:
        return arquivo.read()


def test_csp_libera_o_host_dos_tiles_usados(client):
    """Trocar a base sem liberar o host novo deixaria o mapa em branco."""
    import re as _re
    csp = client.get('/').headers['Content-Security-Policy']
    img_src = _re.search(r'img-src([^;]*)', csp).group(1)

    codigo = _ler_app_js()
    hosts = set(_re.findall(r'https://\{s\}\.([a-z0-9.]+)/', codigo))
    assert hosts, 'nenhuma camada de tiles encontrada em app.js'
    for host in hosts:
        raiz = host.split('.', 1)[1] if host.count('.') >= 2 else host
        assert raiz in img_src, f'host de tiles {host} nao liberado na CSP'


def test_tema_escuro_do_mapa_vem_de_filtro_css():
    """
    Base escura de terceiro exigiria chave (a CARTO devolve tiles com marca
    d'agua "API KEY REQUIRED" respondendo HTTP 200). O tema sai de um filtro
    aplicado ao painel de tiles.
    """
    css = _ler_style_css()
    assert '.mapa-container .leaflet-tile-pane' in css, (
        'o filtro precisa mirar o painel de tiles; no container inteiro ele '
        'inverteria tambem marcadores, popups e controles'
    )
    # A regra e a que contem o filtro, entre o ultimo seletor e a chave.
    blocos = [t.split('}')[0] for t in css.split('.leaflet-tile-pane')[1:]]
    assert any('filter:' in b and 'invert(' in b for b in blocos), (
        'nenhuma regra de .leaflet-tile-pane aplica filtro'
    )


def test_nenhuma_base_de_mapa_exige_chave():
    codigo = _ler_app_js()
    for host_com_chave in ('basemaps.cartocdn.com', 'tiles.stadiamaps.com',
                           'api.mapbox.com', 'maps.googleapis.com'):
        assert host_com_chave not in codigo, (
            f'{host_com_chave} exige API key e degrada sem aviso'
        )


def test_marcador_usa_ponto_sinal_e_nao_alfinete():
    codigo = _ler_app_js()
    assert 'function iconeCliente(' in codigo
    assert 'L.divIcon' in codigo
    assert 'icon: iconeCliente(' in codigo

    css = _ler_style_css()
    for classe in ('.ponto-sinal', '.ponto-entrega', '.ponto-retirada', '.ponto-halo'):
        assert classe in css, f'{classe} ausente no CSS'


def test_cores_do_marcador_batem_com_os_badges():
    """O mapa nao pode inventar uma legenda propria."""
    css = _ler_style_css()
    entrega = css.split('.ponto-entrega')[1].split('}')[0]
    retirada = css.split('.ponto-retirada')[1].split('}')[0]
    assert '#10b981' in entrega   # mesma cor de .badge-entrega
    assert '#f59e0b' in retirada  # mesma cor de .badge-retirada


def test_banho_ambiente_fica_abaixo_dos_marcadores():
    """
    Os panes do Leaflet: tiles 200-400, marcadores 600. O overlay precisa
    ficar entre os dois -- acima de 600 ele apagaria os proprios pontos.
    """
    import re as _re
    css = _ler_style_css()
    bloco = css.split('.mapa-container::after')[1].split('}')[0]
    z = int(_re.search(r'z-index:\s*(\d+)', bloco).group(1))
    assert 400 < z < 600
    assert 'pointer-events: none' in bloco


def test_pulso_do_marcador_respeita_reducao_de_movimento():
    css = _ler_style_css()
    blocos = [b.split(chr(10) + "}")[0]
              for b in css.split("prefers-reduced-motion")[1:]]
    assert blocos, "nenhum bloco de reducao de movimento"
    assert any("ponto-halo" in b and "animation: none" in b for b in blocos), (
        "o pulso do marcador nao e desligado quando o usuario pede menos movimento"
    )


def test_atribuicao_do_openstreetmap_esta_presente():
    """Exigencia de licenca da fonte dos tiles."""
    assert 'openstreetmap.org/copyright' in _ler_app_js()


def test_mapa_com_um_unico_cliente_mostra_o_bairro():
    """
    fitBounds sobre um bounds sem area vai ao zoom maximo e entrega uma quadra.
    Acontece sempre que so um cliente geocodifica -- comum numa base pequena,
    e era a regra no WebView2, onde o `fetch` da geocodificacao falhava.
    """
    codigo = _ler_app_js()
    assert 'ZOOM_CLIENTE_UNICO' in codigo
    corpo = codigo.split('async function carregarMapaClientes')[1]
    assert 'bounds.length === 1' in corpo
    assert 'setView(bounds[0], ZOOM_CLIENTE_UNICO)' in corpo
    # O caso de varios pontos segue usando fitBounds.
    assert 'fitBounds(bounds' in corpo
