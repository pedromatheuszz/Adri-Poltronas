"""
Licenca de uso do aplicativo: 30 dias de teste, depois compra.

O que isto e, e o que nao e
---------------------------
Isto e um controle COMERCIAL, nao uma protecao de seguranca. O aplicativo roda
inteiro na maquina do cliente -- backend, banco e interface --, entao quem
tiver acesso de administrador aquela maquina pode contornar qualquer bloqueio
que se escreva aqui. Nao existe forma honesta de impedir isso sem um servidor
do vendedor no meio, e este projeto nao tem um.

O que este modulo faz e outra coisa, e essa sim e alcancavel: tornar o
contorno DELIBERADO. Ninguem perde o acesso por engano, ninguem estende o
prazo sem perceber que esta fazendo isso, e o caminho honesto -- pagar -- e o
mais facil de todos.

Onde o estado mora, e por que em dois lugares
----------------------------------------------
Guardado SO no banco, um `restaurar backup` de um arquivo antigo devolveria o
prazo ao que era -- e restaurar backup e uma funcao legitima e documentada
deste app, nao um ataque.

Guardado SO num arquivo do perfil, apagar o arquivo reiniciaria o teste.

Entao vive nos dois, e a reconciliacao e sempre pelo lado mais restritivo: a
instalacao mais ANTIGA das duas vale, a marca d'agua mais NOVA vale, e se
qualquer um dos dois disser "paga", esta paga. Apagar um lado nao ajuda;
restaurar um lado velho tambem nao.

O arquivo e cifrado com DPAPI, como o resto dos segredos do projeto. Isso o
prende a conta do Windows: nao impede o proprio usuario de reescreve-lo, e
impede que ele seja copiado de uma maquina para outra.

O relogio
---------
Atrasar o relogio do sistema estenderia o teste indefinidamente. `visto_em` e
a marca d'agua contra isso: guarda a data mais adiantada ja observada e nunca
retrocede. Um relogio atrasado congela a contagem em vez de reverte-la -- o
teste para de andar, e nao volta.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta

import security

log = logging.getLogger("adri.licenca")

# Trinta dias corridos a partir da primeira abertura.
DIAS_DE_TESTE = 30

# Preco de venda, em centavos -- a mesma convencao que o resto do financeiro
# usa (ver `erp/core/dinheiro.py`). R$ 2.000,00.
VALOR_DA_LICENCA_CENTAVOS = 200000

NOME_DO_ARQUIVO = ".licenca"

# Rotas que respondem mesmo com a licenca vencida, pelo motivo evidente: sao
# elas que permitem sair do bloqueio. Exigir licenca para consultar a licenca
# ou para gerar a cobranca dela trancaria o operador do lado de fora com a
# chave dentro.
#
# Mora aqui, e nao no blueprint, porque `app.py` monta o guarda no topo do
# arquivo e so importa os blueprints no fim -- ler a lista de la exigiria
# antecipar aquele import inteiro por causa de um frozenset.
ROTAS_ISENTAS = frozenset({
    "/api/licenca/status",
    "/api/licenca/cobranca",
    "/api/licenca/verificar",
    "/api/licenca/teste",
})

ESTADO_TESTE = "teste"
ESTADO_PAGA = "paga"
ESTADO_EXPIRADA = "expirada"
ESTADO_DESATIVADA = "desativada"

# Formato ISO sem fuso: o app e de uso local, numa maquina so, e gravar fuso
# aqui daria a impressao de uma precisao que a contagem em DIAS nao tem.
_FORMATO = "%Y-%m-%dT%H:%M:%S"


def _agora() -> datetime:
    return datetime.now().replace(microsecond=0)


def _texto(momento: datetime) -> str:
    return momento.strftime(_FORMATO)


def _data(texto: str | None) -> datetime | None:
    if not texto:
        return None
    try:
        return datetime.strptime(str(texto)[:19], _FORMATO)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Lado 1: o arquivo no perfil do usuario
# ---------------------------------------------------------------------------
def pasta_do_perfil() -> str:
    """Mesma pasta do banco. Import tardio pelo motivo descrito em capacidade.py."""
    import database
    return os.path.dirname(os.path.abspath(database.obter_caminho_banco()))


def caminho_do_arquivo() -> str:
    return os.path.join(pasta_do_perfil(), NOME_DO_ARQUIVO)


def _ler_arquivo() -> dict:
    try:
        with open(caminho_do_arquivo(), encoding="utf-8") as arquivo:
            cifrado = arquivo.read().strip()
    except OSError:
        return {}
    if not cifrado:
        return {}

    texto = security.decifrar(cifrado)
    if texto is None:
        # Cifrado para outra conta do Windows, ou arquivo adulterado. Perder o
        # estado e ruim; aceitar um estado que nao se consegue ler e pior --
        # seria a porta de entrada para "apague o arquivo e ganhe 30 dias".
        log.warning("[LICENCA] Arquivo do perfil ilegivel; ignorado.")
        return {}
    try:
        dados = json.loads(texto)
    except ValueError:
        log.warning("[LICENCA] Arquivo do perfil corrompido; ignorado.")
        return {}
    return dados if isinstance(dados, dict) else {}


def _gravar_arquivo(dados: dict) -> None:
    caminho = caminho_do_arquivo()
    try:
        os.makedirs(os.path.dirname(caminho), exist_ok=True)
        with open(caminho, "w", encoding="utf-8") as arquivo:
            arquivo.write(security.cifrar(json.dumps(dados, ensure_ascii=False)))
        try:
            os.chmod(caminho, 0o600)
        except OSError:
            pass
    except (OSError, RuntimeError) as erro:
        # RuntimeError vem de `security.cifrar` quando o DPAPI nao esta
        # disponivel num executavel empacotado. Nao ha o que fazer alem de
        # registrar: o lado do banco continua valendo.
        log.warning("[LICENCA] Nao foi possivel gravar %s: %s", caminho, erro)


# ---------------------------------------------------------------------------
# Lado 2: a tabela no banco
# ---------------------------------------------------------------------------
def _ler_banco() -> dict:
    import database
    try:
        with database.conectar() as conexao:
            linha = conexao.execute(
                "SELECT instalado_em, visto_em, estado, pagamento_id, pago_em, "
                "referencia, teste_modo, teste_ate, teste_controle_em "
                "FROM licenca LIMIT 1"
            ).fetchone()
    except Exception as erro:
        # Banco novo antes da migration, ou schema de emergencia sem a tabela.
        log.info("[LICENCA] Estado no banco indisponivel: %s", erro)
        return {}
    return dict(linha) if linha else {}


def _gravar_banco(dados: dict) -> None:
    import database
    try:
        with database.conectar() as conexao:
            conexao.execute("DELETE FROM licenca")
            conexao.execute(
                "INSERT INTO licenca (instalado_em, visto_em, estado, "
                "pagamento_id, pago_em, referencia, teste_modo, teste_ate, "
                "teste_controle_em) VALUES (?,?,?,?,?,?,?,?,?)",
                (dados.get("instalado_em", ""), dados.get("visto_em", ""),
                 dados.get("estado", ""), dados.get("pagamento_id", ""),
                 dados.get("pago_em", ""), dados.get("referencia", ""),
                 dados.get("teste_modo", ""), dados.get("teste_ate", ""),
                 dados.get("teste_controle_em", "")),
            )
    except Exception as erro:
        log.warning("[LICENCA] Nao foi possivel gravar no banco: %s", erro)


# ---------------------------------------------------------------------------
# A reconciliacao dos dois lados
# ---------------------------------------------------------------------------
def _reconciliar(do_arquivo: dict, do_banco: dict) -> dict:
    """
    Junta os dois lados sempre pelo mais restritivo.

    Instalacao mais antiga vence, marca d'agua mais nova vence, e pagamento
    registrado em qualquer um dos dois vale nos dois. Apagar um lado nao
    encurta a contagem; restaurar um backup velho tambem nao.
    """
    instalacoes = [d for d in (_data(do_arquivo.get("instalado_em")),
                               _data(do_banco.get("instalado_em"))) if d]
    marcas = [d for d in (_data(do_arquivo.get("visto_em")),
                          _data(do_banco.get("visto_em"))) if d]

    pago = None
    for lado in (do_arquivo, do_banco):
        if lado.get("estado") == ESTADO_PAGA:
            pago = lado
            break

    juntado = {
        "instalado_em": _texto(min(instalacoes)) if instalacoes else "",
        "visto_em": _texto(max(marcas)) if marcas else "",
        "estado": ESTADO_PAGA if pago else ESTADO_TESTE,
        "pagamento_id": (pago or do_arquivo or do_banco).get("pagamento_id", "") or "",
        "pago_em": (pago or {}).get("pago_em", "") or "",
        "referencia": (do_arquivo.get("referencia")
                       or do_banco.get("referencia") or ""),
        "teste_modo": "",
        "teste_ate": "",
        "teste_controle_em": "",
    }
    # Um comando explícito do desenvolvedor é mais novo que o conteúdo de um
    # backup antigo. As duas cópias recebem o mesmo carimbo ao salvar.
    controles = [lado for lado in (do_arquivo, do_banco)
                 if _data(lado.get("teste_controle_em"))]
    if controles:
        controle = max(controles, key=lambda lado: _data(lado.get("teste_controle_em")))
        juntado["teste_modo"] = controle.get("teste_modo", "") or ""
        juntado["teste_ate"] = controle.get("teste_ate", "") or ""
        juntado["teste_controle_em"] = controle.get("teste_controle_em", "") or ""
    return juntado


def _persistir(dados: dict) -> None:
    _gravar_arquivo(dados)
    _gravar_banco(dados)


def _carregar_e_atualizar_marca() -> dict:
    """
    Le os dois lados, cria o registro na primeira execucao e avanca a marca
    d'agua do relogio.
    """
    dados = _reconciliar(_ler_arquivo(), _ler_banco())
    agora = _agora()

    if not dados["instalado_em"]:
        dados["instalado_em"] = _texto(agora)
        dados["referencia"] = dados["referencia"] or _nova_referencia()
        log.info("[LICENCA] Primeira execucao: teste de %s dias iniciado.",
                 DIAS_DE_TESTE)

    marca = _data(dados["visto_em"])
    if marca is None or agora > marca:
        dados["visto_em"] = _texto(agora)

    _persistir(dados)
    return dados


def _nova_referencia() -> str:
    """Identificador desta instalacao, usado como `external_reference` no
    Mercado Pago para ligar o pagamento a esta maquina."""
    import secrets
    return "adri-licenca-" + secrets.token_hex(8)


# ---------------------------------------------------------------------------
# A pergunta que o resto do app faz
# ---------------------------------------------------------------------------
def situacao() -> dict:
    """
    Estado atual da licenca, ja com a marca d'agua avancada.

    `dias_restantes` conta a partir de `visto_em`, e nao de `datetime.now()`:
    com o relogio atrasado os dois coincidem, com o relogio adiantado a marca
    ja incorporou o avanco, e em nenhum dos casos o teste anda para tras.
    """
    dados = _carregar_e_atualizar_marca()
    modo_teste = dados.get("teste_modo", "") or "automatico"

    if dados["estado"] == ESTADO_PAGA:
        return {
            "estado": ESTADO_PAGA,
            "dias_restantes": None,
            "instalado_em": dados["instalado_em"],
            "pago_em": dados["pago_em"],
            "pagamento_id": dados["pagamento_id"],
            "referencia": dados["referencia"],
            "valor_centavos": VALOR_DA_LICENCA_CENTAVOS,
            "teste_modo": modo_teste,
        }

    if modo_teste == "desativado":
        return {
            "estado": ESTADO_DESATIVADA,
            "dias_restantes": None,
            "instalado_em": dados["instalado_em"],
            "pago_em": "",
            "pagamento_id": dados["pagamento_id"],
            "referencia": dados["referencia"],
            "valor_centavos": VALOR_DA_LICENCA_CENTAVOS,
            "teste_modo": modo_teste,
        }

    if modo_teste == "manual":
        liberado_ate = _data(dados.get("teste_ate"))
        marca_manual = _data(dados.get("visto_em")) or _agora()
        restantes_manuais = ((liberado_ate.date() - marca_manual.date()).days
                             if liberado_ate else 0)
        if restantes_manuais > 0:
            return {
                "estado": ESTADO_TESTE,
                "dias_restantes": restantes_manuais,
                "instalado_em": dados["instalado_em"],
                "expira_em": _texto(liberado_ate),
                "pago_em": "",
                "pagamento_id": dados["pagamento_id"],
                "referencia": dados["referencia"],
                "valor_centavos": VALOR_DA_LICENCA_CENTAVOS,
                "teste_modo": modo_teste,
            }

    instalado = _data(dados["instalado_em"]) or _agora()
    referencia = _data(dados["visto_em"]) or _agora()
    fim = instalado + timedelta(days=DIAS_DE_TESTE)
    restantes = (fim.date() - referencia.date()).days

    return {
        "estado": ESTADO_TESTE if restantes > 0 else ESTADO_EXPIRADA,
        "dias_restantes": max(restantes, 0),
        "instalado_em": dados["instalado_em"],
        "expira_em": _texto(fim),
        "pago_em": "",
        "pagamento_id": dados["pagamento_id"],
        "referencia": dados["referencia"],
        "valor_centavos": VALOR_DA_LICENCA_CENTAVOS,
        "teste_modo": modo_teste,
    }


def esta_liberado() -> bool:
    """Verdadeiro enquanto o app pode ser usado: teste vigente ou licenca paga."""
    return situacao()["estado"] in (ESTADO_TESTE, ESTADO_PAGA, ESTADO_DESATIVADA)


def situacao_usuario(user_id: int) -> dict:
    """Retorna o período de teste individual da conta."""
    import database
    conta = database.obter_teste_usuario(user_id)
    if not conta:
        return {
            "estado": ESTADO_EXPIRADA,
            "dias_restantes": 0,
            "teste_modo": "expirado",
            "expira_em": "",
            "valor_centavos": VALOR_DA_LICENCA_CENTAVOS,
        }

    modo = conta.get("teste_modo") or "automatico"
    if modo == "desativado":
        return {
            "estado": ESTADO_DESATIVADA,
            "dias_restantes": None,
            "teste_modo": modo,
            "inicio_em": conta.get("teste_inicio_em", ""),
            "expira_em": "",
            "valor_centavos": VALOR_DA_LICENCA_CENTAVOS,
        }

    fim = _data(conta.get("teste_ate"))
    agora = _agora()
    dias = (fim.date() - agora.date()).days if fim else 0
    return {
        "estado": ESTADO_TESTE if dias > 0 else ESTADO_EXPIRADA,
        "dias_restantes": max(dias, 0),
        "teste_modo": modo,
        "inicio_em": conta.get("teste_inicio_em", ""),
        "expira_em": _texto(fim) if fim else "",
        "valor_centavos": VALOR_DA_LICENCA_CENTAVOS,
    }


def controlar_teste_usuario(user_id: int, acao: str) -> dict | None:
    """Libera mais 30 dias ou desativa o limite de uma conta específica."""
    import database

    conta = database.obter_teste_usuario(user_id)
    if not conta:
        return None
    agora = _agora()
    controle_anterior = _data(conta.get("teste_controle_em"))
    if controle_anterior and agora <= controle_anterior:
        agora = controle_anterior + timedelta(seconds=1)

    if acao == "liberar_30_dias":
        modo = "manual"
        inicio = _texto(agora)
        ate = _texto(agora + timedelta(days=DIAS_DE_TESTE))
    elif acao == "desativar":
        modo = "desativado"
        inicio = conta.get("teste_inicio_em") or _texto(agora)
        ate = ""
    else:
        raise ValueError("Ação de teste inválida.")

    database.gravar_teste_usuario(user_id, modo, inicio, ate, _texto(agora))
    log.info("[LICENCA] Controle do teste atualizado para usuario %s: %s", user_id, modo)
    return situacao_usuario(user_id)


def _momento_do_controle(dados: dict):
    agora = _agora()
    anteriores = [_data(dados.get("visto_em")), _data(dados.get("teste_controle_em"))]
    anteriores = [momento for momento in anteriores if momento]
    base = max([agora, *anteriores])
    controle_anterior = _data(dados.get("teste_controle_em"))
    if controle_anterior and base <= controle_anterior:
        base = controle_anterior + timedelta(seconds=1)
    return base


def liberar_teste_30_dias() -> dict:
    """Reinicia por 30 dias o teste, inclusive depois da expiração automática."""
    dados = _carregar_e_atualizar_marca()
    agora = _momento_do_controle(dados)
    dados["teste_modo"] = "manual"
    dados["teste_ate"] = _texto(agora + timedelta(days=DIAS_DE_TESTE))
    dados["teste_controle_em"] = _texto(agora)
    _persistir(dados)
    log.info("[LICENCA] Período de teste liberado manualmente por %s dias.", DIAS_DE_TESTE)
    return situacao()


def desativar_teste() -> dict:
    """Desativa o vencimento do período de teste nesta instalação."""
    dados = _carregar_e_atualizar_marca()
    agora = _momento_do_controle(dados)
    dados["teste_modo"] = "desativado"
    dados["teste_ate"] = ""
    dados["teste_controle_em"] = _texto(agora)
    _persistir(dados)
    log.info("[LICENCA] Período de teste desativado pelo desenvolvedor.")
    return situacao()


def registrar_pagamento(pagamento_id: str) -> dict:
    """
    Marca a licenca como paga. Chamado apenas depois de o Mercado Pago
    CONFIRMAR o pagamento -- nunca a partir do que o cliente disser.
    """
    dados = _carregar_e_atualizar_marca()
    dados["estado"] = ESTADO_PAGA
    dados["pagamento_id"] = str(pagamento_id or "")
    dados["pago_em"] = _texto(_agora())
    _persistir(dados)
    log.info("[LICENCA] Licenca ativada pelo pagamento %s.", pagamento_id)
    return situacao()


def guardar_pagamento_pendente(pagamento_id: str) -> None:
    """Lembra qual cobranca esta aberta, para a verificacao automatica saber a
    quem perguntar depois de o app ser fechado e reaberto."""
    dados = _carregar_e_atualizar_marca()
    dados["pagamento_id"] = str(pagamento_id or "")
    _persistir(dados)
