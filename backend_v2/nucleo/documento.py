"""
CPF e CNPJ: normalizacao e validacao pelos digitos verificadores.

O v1 nao tinha documento nenhum no cadastro -- o que impede emitir nota, e
deixava o Asaas receber cliente sem CPF. Aqui o documento e opcional, mas
quando informado e validado de verdade: aceitar '11111111111' porque "tem 11
digitos" e o tipo de dado sujo que so aparece na hora de faturar.
"""
from __future__ import annotations

import re

_RE_NAO_DIGITO = re.compile(r'\D')


def apenas_digitos(valor: str) -> str:
    return _RE_NAO_DIGITO.sub('', valor or '')


def _digito(base: str, pesos: list[int]) -> str:
    soma = sum(int(d) * p for d, p in zip(base, pesos))
    resto = soma % 11
    return '0' if resto < 2 else str(11 - resto)


def cpf_valido(valor: str) -> bool:
    numero = apenas_digitos(valor)
    if len(numero) != 11 or numero == numero[0] * 11:
        return False
    d1 = _digito(numero[:9], list(range(10, 1, -1)))
    d2 = _digito(numero[:9] + d1, list(range(11, 1, -1)))
    return numero[9:] == d1 + d2


def cnpj_valido(valor: str) -> bool:
    numero = apenas_digitos(valor)
    if len(numero) != 14 or numero == numero[0] * 14:
        return False
    pesos1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    pesos2 = [6] + pesos1
    d1 = _digito(numero[:12], pesos1)
    d2 = _digito(numero[:12] + d1, pesos2)
    return numero[12:] == d1 + d2


def tipo_documento(valor: str) -> str | None:
    """Devolve 'CPF', 'CNPJ' ou None se nao for um documento valido."""
    numero = apenas_digitos(valor)
    if len(numero) == 11 and cpf_valido(numero):
        return 'CPF'
    if len(numero) == 14 and cnpj_valido(numero):
        return 'CNPJ'
    return None


def formatar(valor: str) -> str:
    numero = apenas_digitos(valor)
    if len(numero) == 11:
        return '%s.%s.%s-%s' % (numero[:3], numero[3:6], numero[6:9], numero[9:])
    if len(numero) == 14:
        return '%s.%s.%s/%s-%s' % (numero[:2], numero[2:5], numero[5:8], numero[8:12], numero[12:])
    return numero
