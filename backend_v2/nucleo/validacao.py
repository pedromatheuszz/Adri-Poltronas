"""
Validacao de entrada nas bordas.

Um coletor em vez de "primeiro erro e sai": quem preenche um pedido com quatro
campos errados prefere ver os quatro de uma vez a descobrir um por requisicao.
Todo servico valida com isto e levanta DadosInvalidos com a lista inteira.
"""
from __future__ import annotations

from datetime import datetime
import re

from .dinheiro import ValorInvalido, para_centavos
from .erros import DadosInvalidos

_RE_DATA = re.compile(r'^\d{4}-\d{2}-\d{2}$')
_RE_HORA = re.compile(r'^([01]\d|2[0-3]):[0-5]\d$')
_RE_CEP = re.compile(r'^\d{5}-?\d{3}$')
_RE_EMAIL = re.compile(r'^[^@\s]+@[^@\s]+\.[a-zA-Z]{2,}$')
_RE_UF = re.compile(r'^[A-Z]{2}$')

MAX_INTEIRO_SQLITE = 2 ** 63 - 1


def data_valida(texto) -> bool:
    """
    True so para uma data que existe no calendario.

    O regex sozinho aceita '2026-02-31'. O SQLite nao reclama: date() sobre
    data impossivel devolve NULL e a comparacao some em silencio -- foi assim
    que, no v1, titulo com data invalida nunca aparecia como vencido.
    """
    if not _RE_DATA.match(str(texto or '')):
        return False
    try:
        datetime.strptime(str(texto), '%Y-%m-%d')
    except ValueError:
        return False
    return True


def inteiro_positivo(valor):
    """int > 0 dentro do INTEGER de 64 bits, ou None."""
    if valor is None or isinstance(valor, bool):
        return None
    texto = str(valor).strip()
    if not texto.isdigit():
        return None
    numero = int(texto)
    if numero <= 0 or numero > MAX_INTEIRO_SQLITE:
        return None
    return numero


def normalizar_texto(valor, maximo: int) -> str:
    if valor is None:
        return ""
    texto = re.sub(r'\s+', ' ', str(valor).strip())
    return texto[:maximo]


class Coletor:
    """Acumula erros de um payload e os levanta de uma vez."""

    def __init__(self, dados):
        if not isinstance(dados, dict):
            raise DadosInvalidos("Corpo invalido: esperava um objeto JSON.")
        self.dados = dados
        self.erros: list[str] = []
        self.limpo: dict = {}

    # -- campos --------------------------------------------------------------
    def texto(self, campo, *, obrigatorio=False, maximo=255, minimo=0, rotulo=None):
        nome = rotulo or campo
        valor = normalizar_texto(self.dados.get(campo), maximo)
        if obrigatorio and not valor:
            self.erros.append("%s e obrigatorio." % nome)
        elif valor and len(valor) < minimo:
            self.erros.append("%s deve ter ao menos %d caracteres." % (nome, minimo))
        self.limpo[campo] = valor
        return valor

    def inteiro(self, campo, *, obrigatorio=False, padrao=None, minimo=None, rotulo=None):
        nome = rotulo or campo
        bruto = self.dados.get(campo, None)
        if bruto in (None, ''):
            if obrigatorio:
                self.erros.append("%s e obrigatorio." % nome)
            self.limpo[campo] = padrao
            return padrao
        try:
            numero = int(str(bruto).strip())
        except (TypeError, ValueError):
            self.erros.append("%s deve ser um numero inteiro." % nome)
            self.limpo[campo] = padrao
            return padrao
        if minimo is not None and numero < minimo:
            self.erros.append("%s deve ser maior ou igual a %d." % (nome, minimo))
        if abs(numero) > MAX_INTEIRO_SQLITE:
            self.erros.append("%s excede o limite do banco." % nome)
            numero = padrao
        self.limpo[campo] = numero
        return numero

    def referencia(self, campo, *, obrigatorio=True, rotulo=None):
        """Id de outra entidade: inteiro positivo dentro do limite do SQLite."""
        nome = rotulo or campo
        bruto = self.dados.get(campo)
        if bruto in (None, ''):
            if obrigatorio:
                self.erros.append("%s e obrigatorio." % nome)
            self.limpo[campo] = None
            return None
        numero = inteiro_positivo(bruto)
        if numero is None:
            self.erros.append("%s invalido." % nome)
        self.limpo[campo] = numero
        return numero

    def dinheiro(self, campo, *, obrigatorio=False, padrao=0, minimo=0,
                 rotulo=None, destino=None):
        """
        Devolve CENTAVOS. Aceita 1234.56, '1.234,56' e Decimal.

        `destino` separa o nome de ENTRADA do nome de ARMAZENAMENTO: a API
        recebe `preco_venda` (natural para quem chama) e o banco guarda
        `preco_venda_centavos` (explicito sobre a escala). Sem isso, ou a API
        fica feia ou a coluna mente sobre a unidade -- e ler um campo com um
        nome e grava-lo com outro foi exatamente o defeito que fez o preco
        chegar zerado no catalogo.
        """
        nome = rotulo or campo
        chave = destino or campo
        # A API aceita DUAS formas do mesmo valor, e a exata tem prioridade:
        #   valor_centavos: 81000   -> inteiro, sem conversao
        #   valor: "810,00" | 810.0 -> unidade humana, convertida
        # Sem a forma exata, um cliente que devolvesse o `saldo_centavos` lido
        # da propria API dentro de `valor` teria o numero multiplicado por 100.
        # Nao e hipotese: e o erro de escala classico de integracao financeira.
        chave_exata = chave if chave.endswith('_centavos') else (campo + '_centavos')
        bruto_exato = self.dados.get(chave_exata, None)
        if bruto_exato not in (None, '') and not isinstance(bruto_exato, bool):
            try:
                centavos = int(bruto_exato)
            except (TypeError, ValueError):
                self.erros.append("%s deve ser um inteiro de centavos." % chave_exata)
                self.limpo[chave] = padrao
                return padrao
            if minimo is not None and centavos < minimo:
                self.erros.append("%s nao pode ser menor que %d centavos." % (nome, minimo))
            self.limpo[chave] = centavos
            return centavos

        bruto = self.dados.get(campo, None)
        if bruto in (None, ''):
            if obrigatorio:
                self.erros.append("%s e obrigatorio." % nome)
            self.limpo[chave] = padrao
            return padrao
        try:
            centavos = para_centavos(bruto)
        except ValorInvalido as erro:
            self.erros.append("%s: %s" % (nome, erro))
            self.limpo[chave] = padrao
            return padrao
        if minimo is not None and centavos < minimo:
            self.erros.append("%s nao pode ser menor que %d centavos." % (nome, minimo))
        self.limpo[chave] = centavos
        return centavos

    def data(self, campo, *, obrigatorio=False, padrao='', rotulo=None):
        nome = rotulo or campo
        valor = str(self.dados.get(campo) or '').strip()
        if not valor:
            if obrigatorio:
                self.erros.append("%s e obrigatoria." % nome)
            self.limpo[campo] = padrao
            return padrao
        if not data_valida(valor):
            self.erros.append("%s invalida. Use AAAA-MM-DD." % nome)
            valor = padrao
        self.limpo[campo] = valor
        return valor

    def hora(self, campo, *, rotulo=None):
        nome = rotulo or campo
        valor = str(self.dados.get(campo) or '').strip()
        if valor and not _RE_HORA.match(valor):
            self.erros.append("%s invalida. Use HH:MM." % nome)
            valor = ''
        self.limpo[campo] = valor
        return valor

    def opcao(self, campo, permitidas, *, padrao=None, obrigatorio=False, rotulo=None):
        nome = rotulo or campo
        valor = str(self.dados.get(campo) or '').strip()
        if not valor:
            if obrigatorio:
                self.erros.append("%s e obrigatorio." % nome)
            valor = padrao
        elif valor not in permitidas:
            self.erros.append(
                "%s invalido. Opcoes: %s." % (nome, ', '.join(sorted(permitidas)))
            )
            valor = padrao
        self.limpo[campo] = valor
        return valor

    def booleano(self, campo, *, padrao=False):
        bruto = self.dados.get(campo, None)
        if bruto is None:
            valor = padrao
        elif isinstance(bruto, bool):
            valor = bruto
        else:
            valor = str(bruto).strip().lower() in ('1', 'true', 'sim', 'on')
        self.limpo[campo] = valor
        return valor

    def cep(self, campo, *, obrigatorio=False, rotulo=None):
        nome = rotulo or campo
        valor = str(self.dados.get(campo) or '').strip()
        if not valor:
            if obrigatorio:
                self.erros.append("%s e obrigatorio." % nome)
            self.limpo[campo] = ''
            return ''
        if not _RE_CEP.match(valor):
            self.erros.append("%s invalido. Use 00000-000." % nome)
            self.limpo[campo] = ''
            return ''
        digitos = valor.replace('-', '')
        formatado = '%s-%s' % (digitos[:5], digitos[5:])
        self.limpo[campo] = formatado
        return formatado

    def email(self, campo, *, rotulo=None):
        nome = rotulo or campo
        valor = str(self.dados.get(campo) or '').strip().lower()
        if valor and not _RE_EMAIL.match(valor):
            self.erros.append("%s invalido." % nome)
            valor = ''
        self.limpo[campo] = valor
        return valor

    def uf(self, campo, *, rotulo=None):
        nome = rotulo or campo
        valor = str(self.dados.get(campo) or '').strip().upper()
        if valor and not _RE_UF.match(valor):
            self.erros.append("%s invalida. Use a sigla de 2 letras." % nome)
            valor = ''
        self.limpo[campo] = valor
        return valor

    def lista(self, campo, *, obrigatoria=True, rotulo=None):
        nome = rotulo or campo
        valor = self.dados.get(campo)
        if valor is None:
            valor = []
        if not isinstance(valor, list):
            self.erros.append("%s deve ser uma lista." % nome)
            valor = []
        if obrigatoria and not valor:
            self.erros.append("%s nao pode ser vazia." % nome)
        self.limpo[campo] = valor
        return valor

    # -- fecho ---------------------------------------------------------------
    def erro(self, mensagem: str) -> None:
        self.erros.append(mensagem)

    def validar(self) -> dict:
        if self.erros:
            raise DadosInvalidos("Dados invalidos.", self.erros)
        return self.limpo
