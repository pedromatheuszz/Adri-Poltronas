"""Contexto da operacao atual para auditoria e rastreabilidade."""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import asdict, dataclass, field
import hashlib
from typing import Mapping


@dataclass(frozen=True)
class ContextoOperacao:
    """Metadados tecnicos da operacao, sem credenciais ou IP em texto puro."""

    origem: str = "backend"
    correlation_id: str = ""
    usuario_id: str = ""
    usuario_identificador: str = ""
    ip_hash: str = ""
    rota: str = ""
    metodo: str = ""
    extra: Mapping[str, object] = field(default_factory=dict)

    def como_dict(self) -> dict[str, object]:
        return asdict(self)


_CONTEXTO_ATUAL: ContextVar[ContextoOperacao] = ContextVar(
    "erp_contexto_operacao",
    default=ContextoOperacao(),
)


def iniciar_contexto(contexto: ContextoOperacao):
    """Define o contexto desta execucao e devolve o token para restaura-lo."""
    return _CONTEXTO_ATUAL.set(contexto)


def encerrar_contexto(token) -> None:
    """Restaura o contexto anterior, inclusive em requisicoes concorrentes."""
    _CONTEXTO_ATUAL.reset(token)


def obter_contexto() -> ContextoOperacao:
    return _CONTEXTO_ATUAL.get()


def anonimizar_ip(ip: str, segredo: str) -> str:
    """Gera identificador correlacionavel sem persistir o endereco IP bruto."""
    if not ip:
        return ""
    material = f"{segredo}:{ip}".encode("utf-8")
    return hashlib.sha256(material).hexdigest()[:24]

