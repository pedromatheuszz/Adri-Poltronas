"""
Validações de entrada dos endpoints de cliente, pagamento e entrega agendada.
Centraliza regras para que frontend e backend fiquem em sincronia.
"""
import re
import time
from datetime import datetime

# Limites razoáveis para um cadastro de cliente
NOME_MIN, NOME_MAX = 2, 120
ENDERECO_MAX = 160
CIDADE_MAX = 80
OBSERVACOES_MAX = 1000
# Valores permitidos para entrega/retirada
OPCOES_ENTREGA = {'Entrega', 'Retirada'}

# CEP: aceita com ou sem máscara, devolve canônico (8 dígitos) ou None
_RE_CEP = re.compile(r"^\d{5}-?\d{3}$")
# Allowlist dos campos de texto do cadastro.
#
# `&`, `#`, `+` e `%` entraram porque boa parte da clientela e pessoa juridica
# e a lista anterior barrava razao social comum: "Moveis & Cia Ltda", "Loja #2",
# "50% Decor". Nenhum deles acrescenta risco -- o SQL e parametrizado, o HTML
# passa por `escaparHtml` no frontend, e a exportacao neutraliza prefixo de
# formula em `planilha.neutralizar_formula`, que ja cobria o `-` aceito aqui
# desde sempre. O sinal de que a regra era arbitraria estava a vista: os mesmos
# caracteres sempre passaram em `observacoes`, que nao usa esta allowlist.
#
# As duas expressoes saem da MESMA classe de proposito. Enquanto eram literais
# separados, ampliar uma e esquecer a outra fazia a mensagem de erro acusar
# caractere que a validacao aceita.
_CLASSE_SEGURA = r"[\w\sÀ-ÿ'.,\-()/&#+%]"
_RE_SEGURO = re.compile(rf"^{_CLASSE_SEGURA}+$", re.UNICODE)
_RE_CARACTERE_SEGURO = re.compile(_CLASSE_SEGURA, re.UNICODE)

# Teto do que a mensagem de erro cita. Sem ele, colar um paragrafo inteiro num
# campo devolveria uma mensagem do tamanho do paragrafo.
MAX_CARACTERES_CITADOS = 5
_RE_DATA = re.compile(r'^\d{4}-\d{2}-\d{2}$')
_RE_HORA = re.compile(r'^([01]\d|2[0-3]):[0-5]\d$')


def _erro_de_caracteres(campo, valor):
    """
    Mensagem que diz QUAL caractere foi recusado.

    "Nome contem caracteres invalidos" obriga o operador a adivinhar por
    tentativa e erro num campo que ele acabou de digitar -- e a resposta
    costuma ser um caractere que ele nem enxerga, como um espaco duro colado
    de outro sistema.
    """
    recusados = []
    for caractere in valor:
        if not _RE_CARACTERE_SEGURO.match(caractere) and caractere not in recusados:
            recusados.append(caractere)
            if len(recusados) == MAX_CARACTERES_CITADOS:
                break
    if not recusados:
        return f"{campo} contem caracteres invalidos."
    return f"{campo} contem caracteres invalidos: {' '.join(recusados)}"


def _normalizar_texto(valor, max_len):
    """Remove espaços nas pontas e colapsa múltiplos espaços internos."""
    if valor is None:
        return ""
    v = str(valor).strip()
    v = re.sub(r"\s+", " ", v)
    return v[:max_len]


def _campo_valido(valor, max_len, obrigatorio=True, min_len=1):
    if not valor or not valor.strip():
        return False if obrigatorio else True
    if len(valor) > max_len:
        return False
    if len(valor.strip()) < min_len:
        return False
    # Bloqueia caracteres de controle que nada têm a ver com endereços
    if any(ord(c) < 32 and c not in '\t\n\r' for c in valor):
        return False
    return True


# Teto do INTEGER do SQLite (8 bytes com sinal).
MAX_INTEIRO_SQLITE = 2 ** 63 - 1


def data_valida(texto) -> bool:
    """
    True quando `texto` e uma data real no formato AAAA-MM-DD.

    O regex sozinho aceitava '2026-13-45'. O SQLite nao reclama: `date()`
    sobre uma data impossivel devolve NULL, e a comparacao some silenciosamente
    -- uma entrega com data invalida nunca aparecia nos alertas, e uma cobranca
    nunca era marcada como atrasada.
    """
    if not _RE_DATA.match(str(texto or '')):
        return False
    try:
        datetime.strptime(texto, '%Y-%m-%d')
    except ValueError:
        return False
    return True


def inteiro_positivo(valor):
    """
    Converte `valor` para um int positivo, ou devolve None se nao der.

    Identificadores chegam como texto (query string, corpo JSON) e eram
    passados direto para int(). Um `?cliente_id=abc` levantava ValueError
    fora de qualquer try, e o handler generico transformava isso num 500 com
    id de correlacao -- ruido no log para o que e apenas entrada invalida.
    """
    if valor is None:
        return None
    texto = str(valor).strip()
    if not texto.isdigit():
        return None
    numero = int(texto)
    if numero <= 0 or numero > MAX_INTEIRO_SQLITE:
        # Acima do INTEGER de 64 bits o sqlite3 levanta OverflowError na
        # propria execucao da query -- de novo um 500 para entrada invalida.
        return None
    return numero


def normalizar_cep(cep):
    """Aceita '12345-678' ou '12345678' e devolve '12345-678'. Retorna None se inválido."""
    if cep is None:
        return None
    s = str(cep).strip()
    if not _RE_CEP.match(s):
        return None
    return f"{s[:5]}-{s[-3:]}"


def validar_cliente(dados):
    """
    Recebe um dict (vindo de request.json) e devolve (cliente_normalizado, lista_erros).
    cliente_normalizado é None se a validação falhou.
    """
    erros = []

    if not isinstance(dados, dict):
        return None, ["Payload invalido (esperava JSON)."]

    nome = _normalizar_texto(dados.get("nome", ""), NOME_MAX)
    if not _campo_valido(nome, NOME_MAX, obrigatorio=True, min_len=NOME_MIN):
        erros.append(f"Nome obrigatorio (entre {NOME_MIN} e {NOME_MAX} caracteres).")
    if nome and not _RE_SEGURO.match(nome):
        erros.append(_erro_de_caracteres("Nome", nome))

    cep_raw = dados.get("cep", "")
    cep = normalizar_cep(cep_raw)
    if not cep:
        erros.append("CEP invalido. Use o formato 00000-000.")

    rua = _normalizar_texto(dados.get("rua", ""), ENDERECO_MAX)
    if not _campo_valido(rua, ENDERECO_MAX, obrigatorio=True):
        erros.append(f"Rua obrigatoria (ate {ENDERECO_MAX} caracteres).")
    if rua and not _RE_SEGURO.match(rua):
        erros.append(_erro_de_caracteres("Rua", rua))

    bairro = _normalizar_texto(dados.get("bairro", ""), ENDERECO_MAX)
    if not _campo_valido(bairro, ENDERECO_MAX, obrigatorio=True):
        erros.append(f"Bairro obrigatorio (ate {ENDERECO_MAX} caracteres).")
    if bairro and not _RE_SEGURO.match(bairro):
        erros.append(_erro_de_caracteres("Bairro", bairro))

    cidade = _normalizar_texto(dados.get("cidade", ""), CIDADE_MAX)
    if not _campo_valido(cidade, CIDADE_MAX, obrigatorio=True):
        erros.append(f"Cidade obrigatoria (ate {CIDADE_MAX} caracteres).")
    if cidade and not _RE_SEGURO.match(cidade):
        erros.append(_erro_de_caracteres("Cidade", cidade))

    entrega_retirada = str(dados.get("entrega_retirada", "")).strip()
    if entrega_retirada not in OPCOES_ENTREGA:
        erros.append("Entrega/Retirada invalido. Escolha 'Entrega' ou 'Retirada'.")

    # Observações: opcional, sem validação de formato, só limite de tamanho
    observacoes = _normalizar_texto(dados.get("observacoes", ""), OBSERVACOES_MAX)

    if erros:
        return None, erros

    return {
        "nome": nome,
        "cep": cep,
        "rua": rua,
        "bairro": bairro,
        "cidade": cidade,
        "entrega_retirada": entrega_retirada,
        "observacoes": observacoes,
    }, []


# -----------------------------------------------------------------------------
# Validacoes de Pagamento
# -----------------------------------------------------------------------------
OPCOES_TIPO_PAGAMENTO = {'Pix', 'Boleto', 'Dinheiro', 'Cartao', 'Outro'}
OPCOES_STATUS_PAGAMENTO = {'Pendente', 'Recebido', 'Atrasado', 'Cancelado'}
VALOR_MINIMO = 0.01
VALOR_MAXIMO = 500000.00


def validar_pagamento(dados):
    """
    Recebe um dict (vindo de request.json) e devolve (pagamento_normalizado, lista_erros).
    pagamento_normalizado e None se a validacao falhou.
    """
    erros = []

    if not isinstance(dados, dict):
        return None, ["Payload invalido (esperava JSON)."]

    cliente_id = inteiro_positivo(dados.get('cliente_id'))
    if cliente_id is None:
        erros.append("Cliente invalido.")

    cliente_nome = _normalizar_texto(dados.get('cliente_nome', ''), NOME_MAX)

    try:
        valor = float(dados.get('valor', 0))
    except (TypeError, ValueError):
        valor = 0
    if valor < VALOR_MINIMO or valor > VALOR_MAXIMO:
        erros.append(f"Valor invalido. Use entre R$ {VALOR_MINIMO:.2f} e R$ {VALOR_MAXIMO:.2f}.")

    descricao = _normalizar_texto(dados.get('descricao', ''), OBSERVACOES_MAX)

    data_vencimento = str(dados.get('data_vencimento', '')).strip()
    if not data_vencimento:
        erros.append("Data de vencimento obrigatoria.")
    else:
        if not data_valida(data_vencimento):
            erros.append("Data de vencimento invalida. Use formato AAAA-MM-DD.")

    tipo_pagamento = str(dados.get('tipo_pagamento', 'Pix')).strip()
    if tipo_pagamento not in OPCOES_TIPO_PAGAMENTO:
        opcoes = ', '.join(sorted(OPCOES_TIPO_PAGAMENTO))
        erros.append(f"Tipo de pagamento invalido. Opcoes: {opcoes}.")

    status = str(dados.get('status', '')).strip()
    if status and status not in OPCOES_STATUS_PAGAMENTO:
        erros.append(f"Status invalido. Opcoes: {', '.join(sorted(OPCOES_STATUS_PAGAMENTO))}.")

    # Data em que o dinheiro efetivamente entrou. E ela que alimenta o
    # faturamento por mes no dashboard, entao precisa do mesmo rigor de
    # formato que a data de vencimento.
    data_pagamento = str(dados.get('data_pagamento', '')).strip()
    if data_pagamento and not data_valida(data_pagamento):
        erros.append("Data de pagamento invalida. Use formato AAAA-MM-DD.")

    if erros:
        return None, erros

    status = status or 'Pendente'
    data_pagamento = _coerir_data_pagamento(status, data_pagamento)

    return {
        'cliente_id': cliente_id,
        'cliente_nome': cliente_nome,
        'valor': round(valor, 2),
        'descricao': descricao,
        'data_vencimento': data_vencimento,
        'tipo_pagamento': tipo_pagamento,
        'status': status,
        'data_pagamento': data_pagamento,
    }, []


def _coerir_data_pagamento(status, data_pagamento):
    """
    Mantem `data_pagamento` coerente com `status`.

    As metricas financeiras leem a coluna sem cruzar com o status, entao os
    dois estados incoerentes precisam ser eliminados na entrada: um
    'Recebido' sem data ficaria fora de qualquer mes da serie de
    faturamento, e uma data em cobranca nao recebida contaria receita que
    nao existe.
    """
    if status == 'Recebido':
        return data_pagamento or time.strftime('%Y-%m-%d')
    return ''


# -----------------------------------------------------------------------------
# Validacoes de Entrega Agendada
# -----------------------------------------------------------------------------
OPCOES_STATUS_ENTREGA = ('Pendente', 'Em andamento', 'Concluida', 'Cancelada')

# Status que encerram a entrega: nada mais a avisar sobre ela.
STATUS_ENTREGA_ENCERRADOS = ('Concluida', 'Cancelada')


def validar_entrega(dados):
    """
    Recebe um dict (vindo de request.json) e devolve (entrega_normalizada, erros).

    O endpoint so checava `if not cliente_id or not data_entrega`, entao
    aceitava um cliente_id que nao existe e uma data em texto livre. A entrega
    era gravada e depois sumia dos alertas, porque `date(data_entrega)` no SQL
    das notificacoes devolvia NULL sem erro nenhum.
    """
    erros = []

    if not isinstance(dados, dict):
        return None, ["Payload invalido (esperava JSON)."]

    cliente_id = inteiro_positivo(dados.get('cliente_id'))
    if cliente_id is None:
        erros.append("Cliente invalido.")

    data_entrega = str(dados.get('data_entrega', '')).strip()
    if not data_entrega:
        erros.append("Data de entrega obrigatoria.")
    elif not data_valida(data_entrega):
        erros.append("Data de entrega invalida. Use formato AAAA-MM-DD.")

    hora_entrega = str(dados.get('hora_entrega', '')).strip()
    if hora_entrega and not _RE_HORA.match(hora_entrega):
        erros.append("Hora de entrega invalida. Use formato HH:MM.")

    descricao = _normalizar_texto(dados.get('descricao', ''), OBSERVACOES_MAX)

    if erros:
        return None, erros

    # Opcional: a entrega pode nascer solta (como sempre nasceu) ou vinculada
    # ao pedido que a originou. Sem esta linha o campo era descartado em
    # silencio e o elo pedido-entrega nunca se formava.
    pedido_id = inteiro_positivo(dados.get('pedido_id')) if dados.get('pedido_id') else None

    return {
        'cliente_id': cliente_id,
        'data_entrega': data_entrega,
        'hora_entrega': hora_entrega,
        'descricao': descricao,
        'pedido_id': pedido_id,
    }, []
