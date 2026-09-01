"""
Peças compartilhadas pelas rotas: unidade de trabalho por requisicao,
tratamento uniforme de erro e formatacao monetaria na saida.
"""
from __future__ import annotations

from functools import wraps

from flask import current_app, jsonify, request

from backend_v2.nucleo.dinheiro import serializar
from backend_v2.nucleo.erros import ErroDeDominio
from backend_v2.nucleo.paginacao import Pagina
from backend_v2.nucleo.unidade_trabalho import UnidadeDeTrabalho


def unidade():
    """
    Uma unidade de trabalho por REQUISICAO, criada sob demanda.

    O `with` fica com quem chama, entao a transacao acompanha exatamente o
    caso de uso -- e nao a vida do processo.
    """
    return UnidadeDeTrabalho(current_app.config['FABRICA_CONEXAO'])


def pagina() -> Pagina:
    return Pagina.de_args(request.args)


def corpo() -> dict:
    dados = request.get_json(silent=True)
    return dados if isinstance(dados, dict) else {}


def argumento(nome: str, padrao: str = '') -> str:
    return (request.args.get(nome) or padrao).strip()


def transacional(funcao):
    """
    Abre a unidade, entrega para a rota e comita no fim.

    Erro de dominio vira resposta com o status que ele declara; qualquer outra
    excecao sobe para o handler global, que devolve 500 generico com id de
    correlacao. A rota nunca escolhe status na mao -- foi assim que o v1 acabou
    com o mesmo caso respondendo 404 num lugar e 500 noutro.
    """
    @wraps(funcao)
    def envelope_(*args, **kwargs):
        with unidade() as u:
            return funcao(u, *args, **kwargs)
    return envelope_


# ---------------------------------------------------------------------------
# Saida
# ---------------------------------------------------------------------------
_SUFIXO = '_centavos'


def com_dinheiro(registro):
    """
    Acrescenta a forma legivel ao lado de cada campo `_centavos`.

    O inteiro CONTINUA na resposta: quem calcula usa ele, quem exibe usa o
    texto. Devolver so o formatado obrigaria cada tela a fazer parsing de
    moeda -- e a primeira que errasse a virgula produziria numero errado.
    """
    if isinstance(registro, list):
        return [com_dinheiro(item) for item in registro]
    if not isinstance(registro, dict):
        return registro

    saida = {}
    for chave, valor in registro.items():
        if isinstance(valor, (dict, list)):
            saida[chave] = com_dinheiro(valor)
            continue
        saida[chave] = valor
        if chave.endswith(_SUFIXO) and isinstance(valor, int):
            saida[chave[: -len(_SUFIXO)]] = serializar(valor)['formatado']
    return saida


def ok(dados, status: int = 200):
    return jsonify(com_dinheiro(dados)), status


def paginado(resultado, pag: Pagina, status: int = 200):
    itens, total = resultado
    return jsonify({
        "itens": com_dinheiro(itens),
        "paginacao": {
            "total": total,
            "limite": pag.limite,
            "deslocamento": pag.deslocamento,
            "tem_proxima": pag.deslocamento + len(itens) < total,
        },
    }), status


def registrar_tratadores(app):
    """Erros de dominio viram JSON com o status declarado pela excecao."""

    @app.errorhandler(ErroDeDominio)
    def _dominio(erro: ErroDeDominio):
        return jsonify(erro.como_dict()), erro.status_http

    return app
