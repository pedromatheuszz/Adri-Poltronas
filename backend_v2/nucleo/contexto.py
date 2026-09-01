"""Contexto da operacao: quem, de onde, sob qual correlacao."""
from __future__ import annotations

from contextvars import ContextVar
from dataclasses import asdict, dataclass, field
from typing import Mapping
import hashlib
import uuid


@dataclass(frozen=True)
class ContextoOperacao:
    """Metadados tecnicos da operacao. Nunca credenciais nem IP em texto puro."""
    origem: str = "backend_v2"
    correlation_id: str = ""
    usuario_id: str = ""
    usuario_nome: str = ""
    ip_hash: str = ""
    rota: str = ""
    metodo: str = ""
    extra: Mapping[str, object] = field(default_factory=dict)

    def como_dict(self) -> dict:
        return asdict(self)


_ATUAL: ContextVar[ContextoOperacao] = ContextVar("erp_contexto", default=ContextoOperacao())


def iniciar(contexto: ContextoOperacao):
    return _ATUAL.set(contexto)


def encerrar(token) -> None:
    _ATUAL.reset(token)


def atual() -> ContextoOperacao:
    return _ATUAL.get()


def novo_correlation_id() -> str:
    return uuid.uuid4().hex


def anonimizar_ip(ip: str, segredo: str) -> str:
    """Correlacionavel entre requisicoes, sem guardar o endereco."""
    if not ip:
        return ""
    return hashlib.sha256(("%s:%s" % (segredo, ip)).encode("utf-8")).hexdigest()[:24]
