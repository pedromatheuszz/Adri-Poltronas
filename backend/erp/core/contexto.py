"""Contexto da operacao atual para auditoria e rastreabilidade."""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import asdict, dataclass, field
import hashlib
from collections.abc import Mapping


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
    """
    Restaura o contexto anterior, inclusive em requisicoes concorrentes.

    Idempotente de proposito. `ContextVar.reset()` levanta RuntimeError quando
    recebe um token ja consumido, e o unico chamador e um `teardown_request`
    do Flask -- que pode rodar duas vezes sobre a mesma requisicao (o
    `test_client` usado como gerenciador de contexto faz exatamente isso).
    Uma excecao levantada no teardown substitui a resposta que ja estava
    pronta por um 500, ou seja: a limpeza derrubaria o que ela deveria estar
    apenas encerrando.
    """
    try:
        _CONTEXTO_ATUAL.reset(token)
    except (RuntimeError, ValueError):
        pass


def obter_contexto() -> ContextoOperacao:
    return _CONTEXTO_ATUAL.get()


def anonimizar_ip(ip: str, segredo: str) -> str:
    """Gera identificador correlacionavel sem persistir o endereco IP bruto."""
    if not ip:
        return ""
    material = f"{segredo}:{ip}".encode()
    return hashlib.sha256(material).hexdigest()[:24]

