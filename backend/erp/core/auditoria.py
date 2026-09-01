"""Ledger append-only de auditoria das operacoes empresariais."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime
from decimal import Decimal
import json
import sqlite3

from .contexto import obter_contexto


_CHAVES_SENSIVEIS = {
    "access_token",
    "api_key",
    "authorization",
    "boleto_url",
    "password",
    "pix_payload",
    "pix_qr_code",
    "refresh_token",
    "secret",
    "senha",
    "token",
}


def _chave_sensivel(chave: object) -> bool:
    nome = str(chave).strip().lower()
    return nome in _CHAVES_SENSIVEIS or nome.endswith("_token") or nome.endswith("_secret")


def _normalizar_seguro(valor, *, chave: object = ""):
    if chave and _chave_sensivel(chave):
        return "[REDACTED]"
    if isinstance(valor, Mapping):
        return {str(k): _normalizar_seguro(v, chave=k) for k, v in valor.items()}
    if hasattr(valor, "keys") and callable(valor.keys):
        return {str(k): _normalizar_seguro(valor[k], chave=k) for k in valor.keys()}
    if isinstance(valor, (list, tuple, set)):
        return [_normalizar_seguro(item) for item in valor]
    if isinstance(valor, (datetime, date, Decimal)):
        return str(valor)
    if valor is None or isinstance(valor, (str, int, float, bool)):
        return valor
    return str(valor)


def _json_seguro(valor) -> str | None:
    if valor is None:
        return None
    return json.dumps(
        _normalizar_seguro(valor),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def registrar_evento(
    conexao: sqlite3.Connection,
    *,
    acao: str,
    entidade: str,
    entidade_id: object = "",
    valores_anteriores=None,
    valores_novos=None,
    contexto_extra: Mapping[str, object] | None = None,
) -> int:
    """Registra auditoria usando a mesma transacao da alteracao de negocio."""
    contexto = obter_contexto()
    metadados = contexto.como_dict()
    if contexto_extra:
        metadados["extra"] = {
            **dict(metadados.get("extra") or {}),
            **dict(contexto_extra),
        }

    cursor = conexao.execute(
        """
        INSERT INTO auditoria_eventos (
            usuario_id, usuario_identificador, acao, entidade, entidade_id,
            valores_anteriores, valores_novos, origem, contexto,
            correlation_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            contexto.usuario_id or None,
            contexto.usuario_identificador or None,
            acao,
            entidade,
            str(entidade_id) if entidade_id not in (None, "") else None,
            _json_seguro(valores_anteriores),
            _json_seguro(valores_novos),
            contexto.origem or "backend",
            _json_seguro(metadados) or "{}",
            contexto.correlation_id or None,
        ),
    )
    return int(cursor.lastrowid)
