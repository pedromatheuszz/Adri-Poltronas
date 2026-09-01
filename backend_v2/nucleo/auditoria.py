"""
Trilha de auditoria append-only.

Gravada com a MESMA conexao (logo, a mesma transacao) da alteracao de negocio.
Se o registro nao entra, a trilha tambem nao -- e vice-versa. Auditoria em
transacao separada e pior que nenhuma: da a impressao de completude e mente
justamente nas falhas parciais, que sao as que interessam investigar.
"""
from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime
from decimal import Decimal
import json
import sqlite3

from .contexto import atual

# Nada aqui entra na trilha em texto claro. `endswith` cobre as variacoes
# (`asaas_token`, `chave_secret`) sem precisar enumerar cada uma.
_CHAVES_SENSIVEIS = frozenset({
    "access_token", "api_key", "authorization", "chave_pix", "cvv",
    "password", "pix_payload", "pix_qr_code", "refresh_token", "secret",
    "senha", "token",
})
_SUFIXOS_SENSIVEIS = ("_token", "_secret", "_senha", "_password", "_key")


def _e_sensivel(chave: object) -> bool:
    nome = str(chave).strip().lower()
    return nome in _CHAVES_SENSIVEIS or nome.endswith(_SUFIXOS_SENSIVEIS)


def _sanear(valor, *, chave: object = ""):
    if chave and _e_sensivel(chave):
        return "[OMITIDO]"
    if isinstance(valor, Mapping):
        return {str(k): _sanear(v, chave=k) for k, v in valor.items()}
    # sqlite3.Row nao e Mapping, mas tem keys().
    if hasattr(valor, "keys") and callable(valor.keys):
        return {str(k): _sanear(valor[k], chave=k) for k in valor.keys()}
    if isinstance(valor, (list, tuple, set)):
        return [_sanear(item) for item in valor]
    if isinstance(valor, (datetime, date, Decimal)):
        return str(valor)
    if valor is None or isinstance(valor, (str, int, float, bool)):
        return valor
    return str(valor)


def _json(valor) -> str | None:
    if valor is None:
        return None
    return json.dumps(_sanear(valor), ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def registrar(
    conexao: sqlite3.Connection,
    *,
    acao: str,
    entidade: str,
    entidade_id=None,
    anteriores=None,
    novos=None,
    extra: Mapping[str, object] | None = None,
) -> int:
    """
    Grava um evento. `acao` segue `modulo.entidade.verbo`
    (ex.: 'vendas.pedido.faturado'), para filtrar por prefixo depois.
    """
    contexto = atual()
    metadados = contexto.como_dict()
    if extra:
        metadados["extra"] = {**dict(metadados.get("extra") or {}), **dict(extra)}

    cursor = conexao.execute(
        """
        INSERT INTO auditoria_eventos (
            acao, entidade, entidade_id, valores_anteriores, valores_novos,
            usuario_id, usuario_nome, origem, correlation_id, contexto
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            acao,
            entidade,
            str(entidade_id) if entidade_id not in (None, "") else None,
            _json(anteriores),
            _json(novos),
            contexto.usuario_id or None,
            contexto.usuario_nome or None,
            contexto.origem or "backend_v2",
            contexto.correlation_id or None,
            _json(metadados) or "{}",
        ),
    )
    return int(cursor.lastrowid)
