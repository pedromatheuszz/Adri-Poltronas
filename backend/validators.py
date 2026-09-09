"""
Validações de entrada para os endpoints de cliente.
Centraliza regras para que frontend e backend fiquem em sincronia.
"""
import re

# Limites razoáveis para um cadastro de cliente
NOME_MIN, NOME_MAX = 2, 120
ENDERECO_MAX = 160
CIDADE_MAX = 80
OBSERVACOES_MAX = 1000
# Valores permitidos para entrega/retirada
OPCOES_ENTREGA = {'Entrega', 'Retirada'}

# CEP: aceita com ou sem máscara, devolve canônico (8 dígitos) ou None
_RE_CEP = re.compile(r"^\d{5}-?\d{3}$")
_RE_SEGURO = re.compile(r"^[\w\sÀ-ÿ'.,\-()/]+$", re.UNICODE)
_RE_DATA = re.compile(r'^\d{4}-\d{2}-\d{2}$')


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
        erros.append("Nome contem caracteres invalidos.")

    cep_raw = dados.get("cep", "")
    cep = normalizar_cep(cep_raw)
    if not cep:
        erros.append("CEP invalido. Use o formato 00000-000.")

    rua = _normalizar_texto(dados.get("rua", ""), ENDERECO_MAX)
    if not _campo_valido(rua, ENDERECO_MAX, obrigatorio=True):
        erros.append(f"Rua obrigatoria (ate {ENDERECO_MAX} caracteres).")
    if rua and not _RE_SEGURO.match(rua):
        erros.append("Rua contem caracteres invalidos.")

    bairro = _normalizar_texto(dados.get("bairro", ""), ENDERECO_MAX)
    if not _campo_valido(bairro, ENDERECO_MAX, obrigatorio=True):
        erros.append(f"Bairro obrigatorio (ate {ENDERECO_MAX} caracteres).")
    if bairro and not _RE_SEGURO.match(bairro):
        erros.append("Bairro contem caracteres invalidos.")

    cidade = _normalizar_texto(dados.get("cidade", ""), CIDADE_MAX)
    if not _campo_valido(cidade, CIDADE_MAX, obrigatorio=True):
        erros.append(f"Cidade obrigatoria (ate {CIDADE_MAX} caracteres).")
    if cidade and not _RE_SEGURO.match(cidade):
        erros.append("Cidade contem caracteres invalidos.")

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
OPCOES_TIPO_PAGAMENTO = {'Pix', 'Boleto'}
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

    cliente_id = dados.get('cliente_id')
    if not cliente_id or not str(cliente_id).isdigit() or int(str(cliente_id)) <= 0:
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
        if not _RE_DATA.match(data_vencimento):
            erros.append("Data de vencimento invalida. Use formato AAAA-MM-DD.")

    tipo_pagamento = str(dados.get('tipo_pagamento', 'Pix')).strip()
    if tipo_pagamento not in OPCOES_TIPO_PAGAMENTO:
        erros.append("Tipo de pagamento invalido. Escolha 'Pix' ou 'Boleto'.")

    status = str(dados.get('status', '')).strip()
    if status and status not in OPCOES_STATUS_PAGAMENTO:
        erros.append(f"Status invalido. Opcoes: {', '.join(OPCOES_STATUS_PAGAMENTO)}.")

    if erros:
        return None, erros

    return {
        'cliente_id': int(str(cliente_id)),
        'cliente_nome': cliente_nome,
        'valor': round(valor, 2),
        'descricao': descricao,
        'data_vencimento': data_vencimento,
        'tipo_pagamento': tipo_pagamento,
        'status': status or 'Pendente',
    }, []
