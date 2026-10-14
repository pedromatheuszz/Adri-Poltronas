# backend/microsoft.py
"""
Ciclo de vida do token Microsoft.

Quem precisa falar com o Graph chama `obter_token_valido()` e recebe um
access_token vivo -- ou `None`, se nao houver como conseguir um. A renovacao
silenciosa acontece aqui dentro, e nao no ponto de uso, para que exportacao
de planilha e consulta de status enxerguem exatamente o mesmo estado.

Contexto: ate esta versao a sessao guardava so o access_token, sem validade e
sem refresh_token. Passada a hora de vida do token, `/api/auth/status` ainda
respondia "logado", a tela continuava mostrando "Conectado (fulano)" com o
botao de exportar habilitado, e a falha so aparecia depois do clique --
"Sessao expirada. Reconecte.". O operador descobria o problema no pior momento
possivel, com os clientes ja selecionados.
"""
from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request

import config
import database

log = logging.getLogger("adri.microsoft")

# Margem antes do vencimento. Renovar em cima da hora deixa a requisicao
# seguinte na corrida entre o relogio local e o da Microsoft; 5 minutos
# cobrem tambem um envio de planilha grande que comece perto do limite.
MARGEM_RENOVACAO_S = 300

# Validade assumida quando a Microsoft nao informa `expires_in`. Conservadora
# de proposito: subestimar custa uma renovacao extra, superestimar custa um
# 401 na cara do operador.
VALIDADE_PADRAO_S = 3600

TIMEOUT_S = 20

# Desfecho de uma tentativa de renovacao. A distincao entre RECUSADO e
# INDISPONIVEL e a razao de este modulo existir com esta forma: so a primeira
# autoriza apagar a sessao local.
RENOVADO = 'renovado'
RECUSADO = 'recusado'
INDISPONIVEL = 'indisponivel'


def _agora() -> int:
    return int(time.time())


def calcular_expiracao(expires_in) -> int:
    """Converte o `expires_in` da Microsoft (segundos) em epoch absoluto."""
    try:
        segundos = int(expires_in)
    except (TypeError, ValueError):
        segundos = VALIDADE_PADRAO_S
    if segundos <= 0:
        segundos = VALIDADE_PADRAO_S
    return _agora() + segundos


def token_expirado(expira_em) -> bool:
    """
    `None` significa sessao gravada por uma versao anterior, que nao registrava
    validade. Nesse caso nao da para afirmar que expirou: o token e tratado
    como valido e, se ja estiver morto, o Graph devolve 401 -- exatamente o
    comportamento que existia antes.
    """
    if not expira_em:
        return False
    return _agora() >= (int(expira_em) - MARGEM_RENOVACAO_S)


def renovar_token(refresh_token: str):
    """
    Troca o refresh_token por um access_token novo.

    Devolve o par `(dados, motivo)`:

    * `(dict, RENOVADO)`    -- a Microsoft respondeu com um token novo;
    * `(None, RECUSADO)`    -- a Microsoft respondeu NEGANDO (refresh_token
                               revogado, expirado, consentimento retirado).
                               A sessao morreu de fato; so um login novo resolve;
    * `(None, INDISPONIVEL)` -- nao houve resposta (sem rede, DNS, timeout).
                               A sessao NAO morreu: nao da para confirmar agora.

    O par existe porque o chamador precisava dessa distincao e nao a tinha: com
    um `None` unico para os dois casos, uma queda de rede de dez segundos
    apagava a sessao local e trancava o operador fora do proprio banco ate
    refazer o fluxo OAuth no navegador -- justamente o oposto do funcionamento
    offline que o produto anuncia.
    """
    payload = {
        'client_id': config.CLIENT_ID,
        'scope': config.ESCOPOS_MICROSOFT,
        'refresh_token': refresh_token,
        'grant_type': 'refresh_token',
        'redirect_uri': config.REDIRECT_URI,
    }
    dados = urllib.parse.urlencode(payload).encode('utf-8')
    requisicao = urllib.request.Request(config.URL_TOKEN_MICROSOFT, data=dados, method='POST')  # noqa: S310 - URL montada de constante do proprio codigo, sempre https

    try:
        with urllib.request.urlopen(requisicao, timeout=TIMEOUT_S) as resposta:  # noqa: S310 - URL montada de constante do proprio codigo, sempre https
            return json.loads(resposta.read().decode('utf-8')), RENOVADO
    except urllib.error.HTTPError as erro:
        # O corpo pode carregar identificadores de conta; o status basta para
        # distinguir uma recusa da falha de rede tratada abaixo.
        log.warning("[RENOVACAO] Microsoft recusou a renovação (HTTP %s).", erro.code)
        # HTTPError e subclasse de URLError, entao precisa vir ANTES dela.
        # A Microsoft respondeu: a recusa e definitiva.
        return None, RECUSADO
    except urllib.error.URLError as erro:
        # Sem rede a sessao nao morreu -- so nao da para confirmar agora.
        log.warning("[RENOVACAO] Sem conexao com a Microsoft: %s", erro.reason)
        return None, INDISPONIVEL
    except TimeoutError as erro:
        # Estourar o timeout tambem e ausencia de resposta, nao recusa.
        log.warning("[RENOVACAO] Microsoft nao respondeu a tempo: %s", erro)
        return None, INDISPONIVEL
    except ValueError as erro:
        # Corpo 200 que nao e JSON: a Microsoft respondeu, mas com algo que nao
        # da para usar. Nao e recusa -- tratar como recusa apagaria a sessao por
        # causa de um portal cativo devolvendo HTML no lugar da resposta.
        log.warning("[RENOVACAO] Resposta inesperada da Microsoft: %s", erro)
        return None, INDISPONIVEL


def obter_token_valido():
    """
    Devolve um access_token utilizavel, renovando quando necessario.

    `None` quando nao ha sessao, quando ela expirou sem refresh_token, quando a
    renovacao foi recusada, ou quando nao foi possivel falar com a Microsoft.

    A sessao local so e apagada nos dois primeiros casos, em que se SABE que ela
    nao autentica mais -- manter uma sessao morta e o que fazia a tela mentir
    para o operador. Quando a Microsoft simplesmente nao responde, a sessao
    fica de pe: o app volta a tentar na proxima chamada, e uma queda de rede
    passageira deixa de custar um login novo no navegador.
    """
    sessao = database.obter_sessao()
    if not sessao:
        return None

    if not token_expirado(sessao.get('expira_em')):
        return sessao['token']

    refresh_token = sessao.get('refresh_token')
    if not refresh_token:
        # Sessao anterior ao `offline_access`: nao ha como renovar.
        log.info("[RENOVACAO] Sessao sem refresh_token; e preciso reconectar.")
        database.excluir_sessao()
        return None

    renovado, motivo = renovar_token(refresh_token)
    if not renovado or not renovado.get('access_token'):
        if motivo == INDISPONIVEL:
            # Nao houve resposta. Nao da para afirmar que a sessao morreu, e
            # apagar por via das duvidas tranca o operador fora do banco local.
            log.info("[RENOVACAO] Sem resposta da Microsoft; sessao preservada.")
            return None
        # Resposta HTTP 200 sem access_token e tao definitiva quanto um erro:
        # a Microsoft respondeu e nao entregou token.
        database.excluir_sessao()
        return None

    novo_token = renovado['access_token']
    database.atualizar_token_sessao(
        novo_token,
        calcular_expiracao(renovado.get('expires_in')),
        # A Microsoft rotaciona o refresh_token em parte das renovacoes; quando
        # vem um novo, ele substitui o anterior.
        renovado.get('refresh_token'),
    )
    log.info("[RENOVACAO] Token Microsoft renovado em silêncio.")
    return novo_token
