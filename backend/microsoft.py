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

    Devolve o dicionario da Microsoft em caso de sucesso, ou `None` quando a
    renovacao e recusada (refresh_token revogado, expirado ou consentimento
    retirado) -- situacao em que so um login novo resolve.
    """
    payload = {
        'client_id': config.CLIENT_ID,
        'scope': config.ESCOPOS_MICROSOFT,
        'refresh_token': refresh_token,
        'grant_type': 'refresh_token',
        'redirect_uri': config.REDIRECT_URI,
    }
    dados = urllib.parse.urlencode(payload).encode('utf-8')
    requisicao = urllib.request.Request(config.URL_TOKEN_MICROSOFT, data=dados, method='POST')

    try:
        with urllib.request.urlopen(requisicao, timeout=TIMEOUT_S) as resposta:
            return json.loads(resposta.read().decode('utf-8'))
    except urllib.error.HTTPError as erro:
        corpo = erro.read().decode('utf-8', errors='replace')
        # O corpo traz o motivo (invalid_grant, consent_required...). Vai para
        # o log, nunca para a resposta HTTP: ele cita identificadores da conta.
        log.warning("[RENOVACAO] Microsoft recusou (HTTP %s): %s", erro.code, corpo[:400])
        return None
    except urllib.error.URLError as erro:
        # Sem rede a sessao nao morreu -- so nao da para confirmar agora.
        log.warning("[RENOVACAO] Sem conexao com a Microsoft: %s", erro.reason)
        return None
    except (ValueError, TimeoutError) as erro:
        log.warning("[RENOVACAO] Resposta inesperada da Microsoft: %s", erro)
        return None


def obter_token_valido():
    """
    Devolve um access_token utilizavel, renovando quando necessario.

    `None` quando nao ha sessao, quando ela expirou sem refresh_token, ou
    quando a renovacao foi recusada. Nos dois ultimos casos a sessao local e
    apagada, porque manter uma sessao que nao autentica e o que fazia a tela
    mentir para o operador.
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

    renovado = renovar_token(refresh_token)
    if not renovado or not renovado.get('access_token'):
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
    log.info("[RENOVACAO] Token renovado em silencio para %s", sessao.get('conta'))
    return novo_token
