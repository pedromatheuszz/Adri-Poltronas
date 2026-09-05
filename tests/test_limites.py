"""
Limites de requisicao, exercitados com TESTING desligado.

POR QUE ESTE ARQUIVO EXISTE
Em TESTING o limitador nao conta -- a suite dispara centenas de requisicoes em
segundos, de um IP so, e bateria em qualquer teto realista. Sem estes testes,
portanto, nenhum limite teria cobertura: seria possivel apertar o teto padrao
por engano e a suite continuaria verde ate alguem reclamar de 429 no uso real.

O QUE MUDOU NA 1.3.1
O teto era `200 por minuto` e `50 por segundo`. Numa rajada de 250 GET
sequenciais, 124 receberam 429. E o limite nao defendia de ninguem: o guarda
de host ja recusa o que nao vem de 127.0.0.1, e a capacidade recusa quem nao
apresenta o token, entao todo o trafego que chega ao limitador e do proprio
aplicativo. Na pratica o teto se aplicava ao app -- uma sincronizacao da fila
offline com muitas operacoes acumuladas batia nele e o operador via falhas sem
causa aparente.

O teto padrao agora existe contra loop acidental. Limite apertado ficou onde ha
custo externo real: cota do Gemini, cobranca criada no Asaas, upload ao
OneDrive.
"""
import os
import sys

import pytest

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(RAIZ, 'backend'))

import capacidade  # noqa: E402
import limites  # noqa: E402

TOKEN_DE_CAPACIDADE = 'token-do-app-nos-limites'
CABECALHOS = {capacidade.NOME_DO_HEADER: TOKEN_DE_CAPACIDADE}
ORIGEM_LOCAL = 'http://localhost'


@pytest.fixture
def cliente(monkeypatch, tmp_path):
    """App com os guardas ligados e uma sessao valida, para que o unico
    motivo possivel de 429 seja o limitador."""
    banco = str(tmp_path / 'limites.db')
    monkeypatch.setenv('ADRI_DB_PATH', banco)
    monkeypatch.setenv(capacidade.VARIAVEL_DE_AMBIENTE, TOKEN_DE_CAPACIDADE)
    monkeypatch.delenv(capacidade.VARIAVEL_DE_DESLIGAMENTO, raising=False)

    import app as modulo_app
    import database

    monkeypatch.setattr(database, 'DB_PATH', banco)
    database.criar_tabela()
    database.salvar_sessao('token-de-teste', 'operador@exemplo.local')

    # O armazenamento e `memory://` e vive no processo: sem zerar, o teste
    # anterior deixaria contagem para este, e a falha apareceria conforme a
    # ordem de execucao.
    limites.limiter.reset()
    modulo_app.app.config['TESTING'] = False
    try:
        with modulo_app.app.test_client() as c:
            yield c
    finally:
        modulo_app.app.config['TESTING'] = True
        limites.limiter.reset()


def _contar_429(cliente, metodo, rota, vezes):
    bloqueadas = 0
    for _ in range(vezes):
        resposta = cliente.open(rota, method=metodo, headers={
            **CABECALHOS, 'Origin': ORIGEM_LOCAL,
        }, json={} if metodo != 'GET' else None)
        if resposta.status_code == 429:
            bloqueadas += 1
    return bloqueadas


# =============================================================================
# O teto padrao
# =============================================================================
def test_rajada_de_250_leituras_nao_bate_no_teto(cliente):
    """A rajada exata da auditoria: com o limite anterior, 124 destas 250
    voltavam 429. Uma sincronizacao da fila offline gera trafego assim."""
    assert _contar_429(cliente, 'GET', '/api/clientes', 250) == 0


def test_o_teto_padrao_continua_existindo(cliente):
    """Elevado nao e removido: ele ainda barra o loop acidental -- um
    `setInterval` de 50 ms que ninguem parou consome 1200 requisicoes por
    minuto."""
    assert limites.LIMITE_PADRAO
    numero = int(limites.LIMITE_PADRAO.split()[0])
    assert 1000 <= numero <= 5000, f"teto de {numero}/min fora do razoavel"


# =============================================================================
# Onde ha custo externo
# =============================================================================
def test_conciliacao_tem_limite_proprio(cliente):
    """Roda sozinha a cada 20 minutos e consulta N cobrancas por rodada. Sem
    a chave do Asaas a rota devolve 503 antes de tocar a rede -- o que importa
    aqui e que, passado o teto, ela devolve 429 antes de tocar a VIEW."""
    bloqueadas = _contar_429(cliente, 'POST', '/api/pagamentos/reconciliar', 30)
    assert bloqueadas > 0, "a conciliacao ficou sem limite"


def test_o_limite_da_conciliacao_cabe_no_uso_normal(cliente):
    """Apertar demais quebraria o proprio app: o teto precisa acomodar a
    rodada automatica mais o operador clicando no botao."""
    numero = int(limites.LIMITE_CONCILIACAO.split()[0])
    assert numero >= 5


@pytest.mark.parametrize('constante', [
    'LIMITE_IA',
    'LIMITE_EMISSAO_DE_COBRANCA',
    'LIMITE_CONCILIACAO',
    'LIMITE_ONEDRIVE',
])
def test_as_rotas_caras_sao_bem_mais_apertadas_que_o_padrao(constante):
    """O ponto do ajuste: o padrao e frouxo porque nao defende de ninguem; o
    aperto fica onde cada chamada gasta cota de terceiro."""
    apertado = int(getattr(limites, constante).split()[0])
    padrao = int(limites.LIMITE_PADRAO.split()[0])
    assert apertado * 10 < padrao, f"{constante} nao esta mais apertado que o padrao"
