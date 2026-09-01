"""
Paginacao obrigatoria nas listagens.

Toda listagem do v1 e `SELECT * ... ORDER BY id DESC` sem LIMIT. Com 4 clientes
nao incomoda; num ERP com anos de movimento de estoque, o primeiro GET derruba
o processo. Aqui o limite tem teto e a resposta sempre diz o total.
"""
from __future__ import annotations

from dataclasses import dataclass

LIMITE_PADRAO = 50
LIMITE_MAXIMO = 200


@dataclass(frozen=True)
class Pagina:
    limite: int = LIMITE_PADRAO
    deslocamento: int = 0

    @classmethod
    def de_args(cls, args) -> "Pagina":
        def inteiro(nome, padrao):
            bruto = (args.get(nome) or '').strip()
            if not bruto:
                return padrao
            try:
                return int(bruto)
            except (TypeError, ValueError):
                return padrao

        limite = inteiro('limite', LIMITE_PADRAO)
        deslocamento = inteiro('deslocamento', 0)
        limite = max(1, min(limite, LIMITE_MAXIMO))
        deslocamento = max(0, deslocamento)
        return cls(limite=limite, deslocamento=deslocamento)


def envelope(itens: list, total: int, pagina: Pagina) -> dict:
    return {
        "itens": itens,
        "paginacao": {
            "total": total,
            "limite": pagina.limite,
            "deslocamento": pagina.deslocamento,
            "tem_proxima": pagina.deslocamento + len(itens) < total,
        },
    }
