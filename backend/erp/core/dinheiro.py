"""
Valor monetario como inteiro de centavos.

`pagamentos.valor` e REAL e faz `round(x, 2)` na borda. Isso funciona ate a
primeira soma longa: 0.1 + 0.2 == 0.30000000000000004 em binario, e um
relatorio com milhares de lancamentos acumula a diferenca ate ela aparecer
como centavo faltando no fechamento.

Aqui o dinheiro e SEMPRE int de centavos -- na memoria, no SQLite e no JSON de
saida. Divisao usa rateio explicito, porque dividir dinheiro sempre sobra.

COSTURA DELIBERADA
As tabelas novas (produtos, pedidos, itens) nascem em centavos. A coluna
`pagamentos.valor` continua REAL: converte-la exige leitura dupla durante uma
versao de compatibilidade e reconciliacao dos totais -- e projeto proprio, com
migration propria. Ate la, a conversao acontece na fronteira entre os dois
mundos, e este modulo e o unico lugar que sabe fazer isso.

Colhido de `backend_v2/nucleo/dinheiro.py` antes da remocao daquele backend.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
import re

CENTAVOS_POR_UNIDADE = 100

_RE_NUMERO_BR = re.compile(r'^-?\d{1,3}(\.\d{3})*(,\d{1,2})?$')
_RE_NUMERO_SIMPLES = re.compile(r'^-?\d+([.,]\d{1,2})?$')


class ValorInvalido(ValueError):
    """Entrada que nao representa um valor monetario."""


def para_centavos(valor) -> int:
    """
    Converte entrada externa em centavos.

    Aceita int (ja em centavos NAO -- ver abaixo), float, Decimal e str.

    ATENCAO a uma armadilha de conversao: um `int` recebido da borda e tratado
    como UNIDADE (10 -> 1000 centavos), nao como centavos. Aceitar as duas
    interpretacoes no mesmo lugar e como se perde dinheiro em integracao.
    """
    if isinstance(valor, bool):
        raise ValorInvalido("Valor booleano nao e monetario.")
    if valor is None:
        raise ValorInvalido("Valor ausente.")

    if isinstance(valor, int):
        decimal = Decimal(valor)
    elif isinstance(valor, Decimal):
        decimal = valor
    elif isinstance(valor, float):
        # str() do float evita arrastar a imprecisao binaria para o Decimal.
        decimal = Decimal(str(valor))
    elif isinstance(valor, str):
        decimal = _texto_para_decimal(valor)
    else:
        raise ValorInvalido("Tipo nao suportado para valor monetario: %s" % type(valor).__name__)

    centavos = (decimal * CENTAVOS_POR_UNIDADE).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
    return int(centavos)


def _texto_para_decimal(texto: str) -> Decimal:
    limpo = texto.strip().replace('R$', '').replace(' ', '')
    if not limpo:
        raise ValorInvalido("Valor vazio.")
    # '1.234,56' (pt-BR) e '1234.56' convivem em planilha importada.
    if _RE_NUMERO_BR.match(limpo) and ',' in limpo:
        limpo = limpo.replace('.', '').replace(',', '.')
    elif _RE_NUMERO_SIMPLES.match(limpo):
        limpo = limpo.replace(',', '.')
    else:
        raise ValorInvalido("Valor monetario mal formado: %r" % texto)
    try:
        return Decimal(limpo)
    except Exception:
        raise ValorInvalido("Valor monetario mal formado: %r" % texto)


def formatar(centavos: int) -> str:
    """Centavos -> 'R$ 1.234,56'. Saida de leitura, nunca de calculo."""
    negativo = centavos < 0
    inteiro, resto = divmod(abs(int(centavos)), CENTAVOS_POR_UNIDADE)
    milhar = f"{inteiro:,}".replace(',', '.')
    return "%sR$ %s,%02d" % ('-' if negativo else '', milhar, resto)


def ratear(centavos: int, partes: int) -> list[int]:
    """
    Divide `centavos` em `partes` sem criar nem sumir com dinheiro.

    Parcelar 100,00 em 3 da 33,33 + 33,33 + 33,34 -- e a sobra vai para a
    PRIMEIRA parcela, nao para a ultima: o cliente paga o centavo a mais agora
    e o total confere desde o primeiro vencimento.
    """
    if partes <= 0:
        raise ValorInvalido("Numero de partes deve ser positivo.")
    base, sobra = divmod(abs(int(centavos)), partes)
    sinal = -1 if centavos < 0 else 1
    return [sinal * (base + (1 if i < sobra else 0)) for i in range(partes)]


def serializar(centavos: int) -> dict:
    """
    Forma canonica no JSON da API.

    Sai o inteiro (para calculo) E o texto (para exibicao). Devolver so o
    formatado obrigaria o cliente a fazer parsing de moeda; devolver so o
    inteiro faz cada tela reimplementar a formatacao, e elas divergem.
    """
    return {"centavos": int(centavos), "formatado": formatar(centavos)}
