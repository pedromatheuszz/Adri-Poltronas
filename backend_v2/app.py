"""
Composicao da aplicacao Flask do v2.

Fabrica em vez de instancia global: os testes montam o app apontando para um
banco temporario sem tocar em variavel de modulo. No v1 o `app` era criado no
import e a suite tinha que reescrever `database.DB_PATH` por fora.
"""
from __future__ import annotations

import logging
import os
import sys
import uuid

from flask import Flask, g, jsonify, request
from werkzeug.exceptions import HTTPException

from backend_v2.banco import conexao as banco
from backend_v2.nucleo import contexto
from backend_v2.nucleo.erros import ErroDeDominio

log = logging.getLogger("adri.v2")

VERSAO_API = "2.0.0"


def criar_app(caminho_banco: str | None = None) -> Flask:
    app = Flask(__name__)
    caminho = caminho_banco or banco.caminho_banco()
    banco.preparar_banco(caminho)

    app.config.update(
        CAMINHO_BANCO=caminho,
        FABRICA_CONEXAO=lambda: banco.conectar(caminho),
        MAX_CONTENT_LENGTH=10 * 1024 * 1024,
        JSON_SORT_KEYS=False,
    )

    _registrar_contexto(app)
    _registrar_erros(app)
    _registrar_rotas(app)
    return app


def _registrar_contexto(app: Flask) -> None:
    @app.before_request
    def _abrir_contexto():
        recebido = (request.headers.get('X-Correlation-ID') or '').strip()
        # Cabecalho de fora nao entra sem conferencia: ele vai para o log e
        # para a trilha de auditoria, e texto livre ali e injecao de log.
        permitidos = set(
            "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.:"
        )
        if not recebido or len(recebido) > 64 or any(c not in permitidos for c in recebido):
            recebido = contexto.novo_correlation_id()

        g.correlation_id = recebido
        g.token_contexto = contexto.iniciar(contexto.ContextoOperacao(
            origem='api_v2',
            correlation_id=recebido,
            rota=request.path,
            metodo=request.method,
            ip_hash=contexto.anonimizar_ip(
                request.remote_addr or '', str(app.config.get('SECRET_KEY') or 'v2')),
        ))

    @app.teardown_request
    def _fechar_contexto(_erro):
        token = getattr(g, 'token_contexto', None)
        if token is not None:
            contexto.encerrar(token)

    @app.after_request
    def _cabecalhos(resposta):
        resposta.headers.setdefault('X-Content-Type-Options', 'nosniff')
        resposta.headers.setdefault('X-Frame-Options', 'DENY')
        resposta.headers.setdefault('Referrer-Policy', 'no-referrer')
        resposta.headers.setdefault('Cache-Control', 'no-store')
        resposta.headers.setdefault('X-Adri-Backend', 'v2')
        correlacao = getattr(g, 'correlation_id', '')
        if correlacao:
            resposta.headers.setdefault('X-Correlation-ID', correlacao)
        return resposta


def _registrar_erros(app: Flask) -> None:
    @app.errorhandler(ErroDeDominio)
    def _dominio(erro: ErroDeDominio):
        # Falha de negocio nao e incidente: sai no status que a excecao declara,
        # sem stack trace e sem poluir o log de erro.
        return jsonify(erro.como_dict()), erro.status_http

    @app.errorhandler(HTTPException)
    def _http(erro: HTTPException):
        return jsonify({"erro": erro.description or erro.name,
                        "codigo": "http_%d" % (erro.code or 500)}), erro.code or 500

    @app.errorhandler(Exception)
    def _inesperado(erro: Exception):
        correlacao = getattr(g, 'correlation_id', uuid.uuid4().hex[:12])
        log.exception("Erro nao tratado [%s]: %s", correlacao, erro)
        # Detalhe interno nunca vai para o cliente: so o id que liga a resposta
        # a linha do log.
        return jsonify({
            "erro": "Erro interno do servidor.",
            "codigo": "erro_interno",
            "correlation_id": correlacao,
        }), 500


def _registrar_rotas(app: Flask) -> None:
    from backend_v2.api.rotas_cadastro import bp_estoque, bp_parceiros, bp_produtos
    from backend_v2.api.rotas_operacoes import bp_compras, bp_financeiro, bp_vendas
    from backend_v2.api.rotas_gestao import bp_gestao
    from backend_v2.api.compatibilidade_frontend import bp_frontend

    for blueprint in (bp_parceiros, bp_produtos, bp_estoque,
                      bp_vendas, bp_compras, bp_financeiro, bp_gestao,
                      bp_frontend):
        app.register_blueprint(blueprint)

    @app.get('/api/v2/saude')
    def saude():
        return jsonify({
            "servico": "Adri Poltronas ERP",
            "versao_api": VERSAO_API,
            "banco": os.path.basename(app.config['CAMINHO_BANCO']),
            "python": sys.version.split()[0],
        })
