"""
Regras do catalogo e do pedido de venda.

Este e o unico lugar que decide: se um pedido pode mudar de situacao, como os
totais sao calculados, e o que acontece no faturamento. Os blueprints em
`backend/blueprints/` sao adaptadores HTTP -- traduzem JSON para chamada de
funcao e erro de dominio para status, sem regra propria.

O FATURAMENTO E O CORACAO DO MODULO
Faturar gera as parcelas a receber e marca o pedido, numa transacao so. Se a
emissao da segunda parcela falhar, a primeira volta atras e o pedido continua
aprovado -- nao fica pedido faturado com cobranca pela metade, que e a
divergencia mais cara de achar depois.
"""
from __future__ import annotations

import datetime
import logging
import sqlite3
from typing import Optional

import database
import validators
from erp.comercial import estados, repositorio
from erp.core import dinheiro
from erp.core.auditoria import registrar_evento

log = logging.getLogger("adri.comercial")

UNIDADES = ("un", "pc", "cj", "m", "m2", "h")
FORMAS_DE_PAGAMENTO = ("Pix", "Boleto", "Dinheiro", "Cartao", "Outro")

MAX_PARCELAS = 36
LIMITE_ITENS_POR_PEDIDO = 200

# Quantas vezes reemitir o numero do pedido quando outro cadastro leva o mesmo.
# Tres cobre com folga o cenario real (dois cliques do mesmo operador); um
# numero alto aqui so mascararia um problema diferente.
TENTATIVAS_DE_NUMERACAO = 3


class ErroDeNegocio(Exception):
    """Regra violada. O blueprint traduz para 400."""


class NaoEncontrado(Exception):
    """Registro inexistente. O blueprint traduz para 404."""


class ConflitoDeSituacao(Exception):
    """Operacao incompativel com a situacao atual. O blueprint traduz para 409."""


# =============================================================================
# Catalogo
# =============================================================================
def _validar_produto(dados: dict, ignorar_id: Optional[int] = None) -> dict:
    codigo = (dados.get("codigo") or "").strip()
    descricao = (dados.get("descricao") or "").strip()
    unidade = (dados.get("unidade") or "un").strip().lower()

    erros = []
    if not codigo or len(codigo) > 40:
        erros.append("Codigo e obrigatorio e deve ter ate 40 caracteres.")
    if not descricao or len(descricao) > 200:
        erros.append("Descricao e obrigatoria e deve ter ate 200 caracteres.")
    if unidade not in UNIDADES:
        erros.append(f"Unidade deve ser uma de: {', '.join(UNIDADES)}.")

    try:
        preco = dinheiro.para_centavos(dados.get("preco_venda", 0))
        if preco < 0:
            erros.append("Preco nao pode ser negativo.")
    except dinheiro.ValorInvalido as erro:
        erros.append(str(erro))
        preco = 0

    if erros:
        raise ErroDeNegocio(" ".join(erros))

    return {
        "codigo": codigo,
        "descricao": descricao,
        "unidade": unidade,
        "preco_venda_centavos": preco,
        "observacoes": (dados.get("observacoes") or "").strip()[:1000],
        "_ignorar_id": ignorar_id,
    }


def listar_produtos(busca: str = "", incluir_inativos: bool = False) -> list[dict]:
    with database.conectar() as conexao:
        return [_produto_para_tela(p) for p in
                repositorio.listar_produtos(conexao, busca, incluir_inativos)]


def _produto_para_tela(produto: dict) -> dict:
    """Acrescenta o valor formatado para a tela nao reimplementar moeda."""
    produto = dict(produto)
    produto["preco_venda"] = dinheiro.serializar(produto["preco_venda_centavos"])
    return produto


def _codigo_duplicado(erro: sqlite3.IntegrityError, codigo: str) -> ErroDeNegocio:
    """
    Traduz a recusa do indice unico para o MESMO erro da checagem previa.

    A checagem `codigo_em_uso` roda num SELECT fora de transacao, entao dois
    cadastros simultaneos com o mesmo codigo passam os dois por ela. O indice
    unico pega o segundo -- e sem esta traducao ele chegava ao operador como
    500 com id de correlacao, quando a resposta certa e exatamente a mensagem
    que ele teria recebido se tivesse chegado um segundo depois.
    """
    if "produtos.codigo" not in str(erro):
        raise erro
    return ErroDeNegocio(f"Ja existe um produto ativo com o codigo {codigo}.")


def criar_produto(dados: dict) -> dict:
    campos = _validar_produto(dados)
    try:
        with database.conectar() as conexao:
            if repositorio.codigo_em_uso(conexao, campos["codigo"]):
                raise ErroDeNegocio(
                    f"Ja existe um produto ativo com o codigo {campos['codigo']}.")
            produto_id = repositorio.inserir_produto(conexao, campos)
            novo = repositorio.obter_produto(conexao, produto_id)
            registrar_evento(conexao, acao="comercial.produto.criado", entidade="produto",
                             entidade_id=produto_id, valores_novos=novo)
    except sqlite3.IntegrityError as erro:
        raise _codigo_duplicado(erro, campos["codigo"])
    return _produto_para_tela(novo)


def atualizar_produto(produto_id: int, dados: dict) -> dict:
    campos = _validar_produto(dados, ignorar_id=produto_id)
    try:
        with database.conectar() as conexao:
            anterior = repositorio.obter_produto(conexao, produto_id)
            if anterior is None:
                raise NaoEncontrado("Produto nao encontrado.")
            if repositorio.codigo_em_uso(conexao, campos["codigo"], ignorar_id=produto_id):
                raise ErroDeNegocio(
                    f"Ja existe um produto ativo com o codigo {campos['codigo']}.")
            repositorio.atualizar_produto(conexao, produto_id, campos)
            novo = repositorio.obter_produto(conexao, produto_id)
            registrar_evento(conexao, acao="comercial.produto.alterado", entidade="produto",
                             entidade_id=produto_id, valores_anteriores=anterior,
                             valores_novos=novo)
    except sqlite3.IntegrityError as erro:
        raise _codigo_duplicado(erro, campos["codigo"])
    return _produto_para_tela(novo)


def inativar_produto(produto_id: int) -> None:
    with database.conectar() as conexao:
        anterior = repositorio.obter_produto(conexao, produto_id)
        if anterior is None:
            raise NaoEncontrado("Produto nao encontrado.")
        repositorio.inativar_produto(conexao, produto_id)
        registrar_evento(conexao, acao="comercial.produto.inativado", entidade="produto",
                         entidade_id=produto_id, valores_anteriores=anterior)


# =============================================================================
# Pedido
# =============================================================================
def _hoje() -> str:
    return datetime.date.today().isoformat()


def _exigir_pedido(conexao, pedido_id: int) -> dict:
    pedido = repositorio.obter_pedido(conexao, pedido_id)
    if pedido is None:
        raise NaoEncontrado("Pedido nao encontrado.")
    return pedido


def _exigir_editavel(pedido: dict) -> None:
    if not estados.e_editavel(pedido["situacao"]):
        raise ConflitoDeSituacao(
            f"O pedido {pedido['numero']} esta em '{pedido['situacao']}' e nao aceita "
            "mais alteracao de itens."
        )


def _recalcular(conexao, pedido_id: int) -> dict:
    """
    Totais sao GRAVADOS, nao calculados na leitura.

    Se fossem derivados na hora, editar o preco de um produto no catalogo
    reescreveria o valor de pedidos ja fechados -- inclusive dos faturados.
    """
    pedido = _exigir_pedido(conexao, pedido_id)
    bruto = repositorio.somar_itens(conexao, pedido_id)
    liquido = bruto - int(pedido["desconto_centavos"]) + int(pedido["frete_centavos"])
    if liquido < 0:
        raise ErroDeNegocio("O desconto deixa o total do pedido negativo.")
    repositorio.atualizar_totais(conexao, pedido_id, bruto, liquido)
    return repositorio.obter_pedido(conexao, pedido_id)


def _pedido_para_tela(pedido: dict, itens: Optional[list] = None) -> dict:
    pedido = dict(pedido)
    for campo in ("total_bruto_centavos", "desconto_centavos",
                  "frete_centavos", "total_liquido_centavos"):
        pedido[campo.replace("_centavos", "")] = dinheiro.serializar(pedido[campo])
    # A tela usa isto para decidir quais botoes mostrar, em vez de repetir a
    # maquina de estados em JavaScript e arriscar divergir do backend.
    pedido["proximos_passos"] = list(estados.proximos_passos(pedido["situacao"]))
    pedido["editavel"] = estados.e_editavel(pedido["situacao"])
    pedido["aceita_entrega"] = estados.aceita_entrega(pedido["situacao"])
    if itens is not None:
        pedido["itens"] = [_item_para_tela(i) for i in itens]
    return pedido


def _item_para_tela(item: dict) -> dict:
    item = dict(item)
    item["preco_unitario"] = dinheiro.serializar(item["preco_unitario_centavos"])
    item["total"] = dinheiro.serializar(item["total_centavos"])
    return item


def listar_pedidos(situacao: str = "", busca: str = "") -> list[dict]:
    with database.conectar() as conexao:
        return [_pedido_para_tela(p) for p in
                repositorio.listar_pedidos(conexao, situacao, busca)]


def _parcela_para_tela(parcela: dict) -> dict:
    """
    Acrescenta o que a tela precisa e o banco nao guarda.

    `em_atraso` e DERIVADO do vencimento, nunca gravado. Gravar 'Atrasado'
    exigiria uma rotina passando meia-noite para reescrever linhas, e uma
    parcela vencida ontem apareceria como em dia ate essa rotina rodar. O
    status gravado responde "o que o operador declarou"; `em_atraso` responde
    "o que o calendario diz", e as duas perguntas sao diferentes.
    """
    saida = dict(parcela)
    saida["valor"] = dinheiro.serializar(int(parcela.get("valor_centavos") or 0))
    saida["em_atraso"] = bool(
        parcela.get("status") == "Pendente"
        and parcela.get("data_vencimento")
        and str(parcela["data_vencimento"]) < _hoje()
    )
    return saida


def obter_pedido(pedido_id: int) -> dict:
    with database.conectar() as conexao:
        pedido = repositorio.obter_pedido_com_itens(conexao, pedido_id)
        if pedido is None:
            raise NaoEncontrado("Pedido nao encontrado.")
        completo = _pedido_para_tela(pedido, pedido["itens"])
        completo["parcelas"] = [
            _parcela_para_tela(p) for p in repositorio.parcelas_do_pedido(conexao, pedido_id)]
        completo["entregas"] = repositorio.entregas_do_pedido(conexao, pedido_id)
    return completo


# Status que o operador pode declarar numa parcela.
#
# 'Atrasado' fica de fora de proposito: ele e derivado do vencimento
# (`em_atraso`), nao declarado. Deixar o operador marcar 'Atrasado' criaria dois
# donos para a mesma verdade, e nenhum deles confiavel.
STATUS_DE_PARCELA = ("Recebido", "Pendente", "Cancelado")


def baixar_parcela(pedido_id: int, parcela: int, dados: dict) -> dict:
    """
    Dá baixa numa parcela do pedido, ou desfaz uma baixa.

    Esta funcao e o outro lado do faturamento. Ate a 1.5.0 o faturamento
    emitia as parcelas e nao havia nada no aplicativo que as lesse, muito menos
    que as recebesse: o ciclo terminava com dinheiro registrado a receber e sem
    caminho de volta. O pedido, por desenho, vira terminal ao ser faturado --
    entao o recebimento nao tinha onde acontecer.
    """
    numero = validators.inteiro_positivo(parcela)
    if numero is None:
        raise ErroDeNegocio("Numero de parcela invalido.")

    status = (dados.get("status") or "").strip()
    if status not in STATUS_DE_PARCELA:
        raise ErroDeNegocio(
            f"Status deve ser um de: {', '.join(STATUS_DE_PARCELA)}.")

    data_pagamento = (dados.get("data_pagamento") or "").strip()
    if status == "Recebido":
        # Sem data informada, o recebimento e hoje: e o caso esmagadoramente
        # mais comum (o operador marca no momento em que recebe) e exigir o
        # campo so acrescentaria um clique a operacao mais frequente.
        data_pagamento = data_pagamento or _hoje()
        if not validators.data_valida(data_pagamento):
            raise ErroDeNegocio("Data de pagamento invalida.")
    else:
        # Desfazer a baixa tem de limpar a data. Uma parcela 'Pendente' com
        # data de pagamento preenchida e a contradicao que faz relatorio mentir.
        data_pagamento = ""

    with database.conectar() as conexao:
        atual = repositorio.obter_parcela(conexao, pedido_id, numero)
        if atual is None:
            raise NaoEncontrado("Parcela nao encontrada.")
        if atual["status"] == status:
            raise ConflitoDeSituacao(f"A parcela {numero} ja esta '{status}'.")

        alteradas = repositorio.mudar_status_da_parcela(
            conexao, pedido_id, numero, status, data_pagamento,
            status_esperado=atual["status"])
        if alteradas == 0:
            raise ConflitoDeSituacao(
                f"A parcela {numero} mudou durante a operacao. Recarregue a tela.")

        nova = repositorio.obter_parcela(conexao, pedido_id, numero)
        registrar_evento(conexao, acao="comercial.parcela.baixa", entidade="pagamento",
                         entidade_id=int(nova["id"]), valores_anteriores=atual,
                         valores_novos=nova)
    return _parcela_para_tela(nova)


def _validar_cabecalho(conexao, dados: dict) -> dict:
    cliente_id = validators.inteiro_positivo(dados.get("cliente_id"))
    if cliente_id is None:
        raise ErroDeNegocio("Cliente e obrigatorio.")
    cliente = database.obter_cliente_por_id(cliente_id)
    if cliente is None:
        raise NaoEncontrado("Cliente nao encontrado.")

    prazo = (dados.get("data_entrega_prevista") or "").strip()
    if prazo and not validators.data_valida(prazo):
        raise ErroDeNegocio("Data de entrega prevista invalida.")

    try:
        desconto = dinheiro.para_centavos(dados.get("desconto", 0))
        frete = dinheiro.para_centavos(dados.get("frete", 0))
    except dinheiro.ValorInvalido as erro:
        raise ErroDeNegocio(str(erro))
    if desconto < 0 or frete < 0:
        raise ErroDeNegocio("Desconto e frete nao podem ser negativos.")

    return {
        "cliente_id": cliente_id,
        "cliente_nome": cliente["nome"],
        "data_entrega_prevista": prazo,
        "desconto_centavos": desconto,
        "frete_centavos": frete,
        "observacoes": (dados.get("observacoes") or "").strip()[:1000],
    }


def criar_pedido(dados: dict) -> dict:
    """
    Cria o pedido, reemitindo o numero se alguem levar o mesmo primeiro.

    `proximo_numero()` deriva do maior numero ja gravado, com um SELECT que
    roda fora de transacao (o sqlite3 do Python so abre uma na primeira
    escrita). Dois cadastros simultaneos liam o mesmo ultimo numero e tentavam
    gravar o mesmo seguinte: o indice unico recusava a segunda e o handler
    generico devolvia 500 com id de correlacao.

    Um 500 e a resposta errada aqui. O operador nao fez nada de errado, e o
    sistema sabe exatamente o que aconteceu -- basta pegar o numero seguinte.
    O indice unico continua sendo a autoridade; o retry so aceita a resposta
    dele em vez de morrer com ela.
    """
    exercicio = str(datetime.date.today().year)
    for tentativa in range(TENTATIVAS_DE_NUMERACAO):
        try:
            with database.conectar() as conexao:
                campos = _validar_cabecalho(conexao, dados)
                campos["numero"] = repositorio.proximo_numero(conexao, exercicio)
                campos["data_emissao"] = _hoje()
                pedido_id = repositorio.inserir_pedido(conexao, campos)
                novo = repositorio.obter_pedido(conexao, pedido_id)
                registrar_evento(conexao, acao="comercial.pedido.criado", entidade="pedido",
                                 entidade_id=pedido_id, valores_novos=novo)
            return _pedido_para_tela(novo, [])
        except sqlite3.IntegrityError as erro:
            # So a colisao de numero e reversivel por retry. Qualquer outra
            # violacao de integridade (FK para cliente inexistente, por
            # exemplo) e um erro de verdade e precisa subir.
            if "pedidos.numero" not in str(erro):
                raise
            log.warning("[PEDIDO] Numero disputado na tentativa %s: %s", tentativa + 1, erro)

    raise ConflitoDeSituacao(
        "Nao foi possivel reservar um numero de pedido. Tente novamente.")


def atualizar_pedido(pedido_id: int, dados: dict) -> dict:
    with database.conectar() as conexao:
        pedido = _exigir_pedido(conexao, pedido_id)
        _exigir_editavel(pedido)
        campos = _validar_cabecalho(conexao, dados)
        repositorio.atualizar_cabecalho(conexao, pedido_id, campos)
        atualizado = _recalcular(conexao, pedido_id)
        registrar_evento(conexao, acao="comercial.pedido.alterado", entidade="pedido",
                         entidade_id=pedido_id, valores_anteriores=pedido,
                         valores_novos=atualizado)
        itens = repositorio.listar_itens(conexao, pedido_id)
    return _pedido_para_tela(atualizado, itens)


# --- Itens -------------------------------------------------------------------
def adicionar_item(pedido_id: int, dados: dict) -> dict:
    with database.conectar() as conexao:
        pedido = _exigir_pedido(conexao, pedido_id)
        _exigir_editavel(pedido)

        if len(repositorio.listar_itens(conexao, pedido_id)) >= LIMITE_ITENS_POR_PEDIDO:
            raise ErroDeNegocio(f"Um pedido aceita no maximo {LIMITE_ITENS_POR_PEDIDO} itens.")

        produto_id = validators.inteiro_positivo(dados.get("produto_id"))
        if produto_id is None:
            raise ErroDeNegocio("Produto e obrigatorio.")
        produto = repositorio.obter_produto(conexao, produto_id)
        if produto is None or not produto["ativo"]:
            raise NaoEncontrado("Produto nao encontrado ou inativo.")

        quantidade = validators.inteiro_positivo(dados.get("quantidade", 1))
        if quantidade is None:
            raise ErroDeNegocio("Quantidade deve ser um inteiro positivo.")

        try:
            # Preco cai para o do catalogo quando nao vem informado, mas pode
            # ser sobrescrito: encomenda negocia valor caso a caso.
            bruto = dados.get("preco_unitario")
            preco = (dinheiro.para_centavos(bruto) if bruto not in (None, "")
                     else int(produto["preco_venda_centavos"]))
            desconto = dinheiro.para_centavos(dados.get("desconto", 0))
        except dinheiro.ValorInvalido as erro:
            raise ErroDeNegocio(str(erro))

        total = preco * quantidade - desconto
        if total < 0:
            raise ErroDeNegocio("O desconto do item supera o valor dele.")

        # Descricao propria: cada poltrona tem tecido, acabamento e medida.
        # Sem informar, herda a do catalogo.
        descricao = (dados.get("descricao") or "").strip() or produto["descricao"]

        repositorio.inserir_item(conexao, pedido_id, {
            "produto_id": produto_id,
            "descricao": descricao[:300],
            "quantidade": quantidade,
            "preco_unitario_centavos": preco,
            "desconto_centavos": desconto,
            "total_centavos": total,
        })
        atualizado = _recalcular(conexao, pedido_id)
        itens = repositorio.listar_itens(conexao, pedido_id)
        registrar_evento(conexao, acao="comercial.pedido.item_adicionado", entidade="pedido",
                         entidade_id=pedido_id, valores_novos=atualizado)
    return _pedido_para_tela(atualizado, itens)


def remover_item(pedido_id: int, item_id: int) -> dict:
    with database.conectar() as conexao:
        pedido = _exigir_pedido(conexao, pedido_id)
        _exigir_editavel(pedido)
        if repositorio.remover_item(conexao, pedido_id, item_id) == 0:
            raise NaoEncontrado("Item nao encontrado neste pedido.")
        atualizado = _recalcular(conexao, pedido_id)
        itens = repositorio.listar_itens(conexao, pedido_id)
        registrar_evento(conexao, acao="comercial.pedido.item_removido", entidade="pedido",
                         entidade_id=pedido_id, valores_novos=atualizado)
    return _pedido_para_tela(atualizado, itens)


# --- Transicoes --------------------------------------------------------------
def _transicionar(conexao, pedido: dict, destino: str, extras: Optional[dict] = None) -> dict:
    """
    Move o pedido de situacao, recusando se outro ja tiver movido.

    A checagem da maquina de estados vale sobre o que ESTA REQUISICAO leu; e a
    leitura acontece fora de transacao, porque o sqlite3 do Python so abre uma
    na primeira escrita. Passar `situacao_esperada` faz o proprio UPDATE
    revalidar a premissa no momento da escrita: se ninguem mexeu, uma linha
    muda; se outra requisicao chegou primeiro, zero -- e a segunda vira 409 em
    vez de gravar por cima.
    """
    try:
        estados.exigir_transicao(pedido["situacao"], destino, pedido["numero"])
    except estados.TransicaoInvalida as erro:
        raise ConflitoDeSituacao(str(erro))

    alteradas = repositorio.mudar_situacao(
        conexao, pedido["id"], destino, extras, situacao_esperada=pedido["situacao"])
    if alteradas == 0:
        raise ConflitoDeSituacao(
            f"O pedido {pedido['numero']} mudou de situacao durante a operacao. "
            "Recarregue a tela e tente de novo."
        )
    return repositorio.obter_pedido(conexao, pedido["id"])


def abrir_pedido(pedido_id: int) -> dict:
    with database.conectar() as conexao:
        pedido = _exigir_pedido(conexao, pedido_id)
        if not repositorio.listar_itens(conexao, pedido_id):
            raise ErroDeNegocio("Um pedido sem itens nao pode ser aberto.")
        atualizado = _transicionar(conexao, pedido, estados.ABERTO)
        registrar_evento(conexao, acao="comercial.pedido.aberto", entidade="pedido",
                         entidade_id=pedido_id, valores_anteriores=pedido,
                         valores_novos=atualizado)
    return _pedido_para_tela(atualizado)


def aprovar_pedido(pedido_id: int) -> dict:
    with database.conectar() as conexao:
        pedido = _exigir_pedido(conexao, pedido_id)
        atualizado = _transicionar(conexao, pedido, estados.APROVADO)
        registrar_evento(conexao, acao="comercial.pedido.aprovado", entidade="pedido",
                         entidade_id=pedido_id, valores_anteriores=pedido,
                         valores_novos=atualizado)
    return _pedido_para_tela(atualizado)


def cancelar_pedido(pedido_id: int, motivo: str = "") -> dict:
    """
    Cancela o pedido E as entregas que so existiam por causa dele.

    O cancelamento so mudava a situacao do pedido. As entregas vinculadas
    continuavam 'Pendente' na agenda e seguiam gerando notificacao
    "ENTREGA ATRASADA" para um pedido que ninguem ia mais entregar -- alerta
    que nao corresponde a nada e o que ensina o operador a ignorar alertas.

    Tudo na mesma transacao: pedido cancelado com entrega viva e o mesmo tipo
    de meia-verdade que o faturamento evita ao emitir as parcelas de uma vez.
    """
    with database.conectar() as conexao:
        pedido = _exigir_pedido(conexao, pedido_id)
        atualizado = _transicionar(conexao, pedido, estados.CANCELADO, {
            "cancelado_em": datetime.datetime.now().isoformat(timespec="seconds"),
            "motivo_cancelamento": (motivo or "").strip()[:500],
        })
        entregas_canceladas = repositorio.cancelar_entregas_do_pedido(conexao, pedido_id)
        registrar_evento(conexao, acao="comercial.pedido.cancelado", entidade="pedido",
                         entidade_id=pedido_id, valores_anteriores=pedido,
                         valores_novos=atualizado,
                         contexto_extra={"entregas_canceladas": entregas_canceladas})
    resultado = _pedido_para_tela(atualizado)
    resultado["entregas_canceladas"] = entregas_canceladas
    return resultado


def _vencimentos_mensais(primeiro: str, parcelas: int) -> list[str]:
    """
    Serie mensal a partir do primeiro vencimento.

    Dia 31 em mes de 30 cai para o ultimo dia do mes, em vez de estourar --
    parcelamento comecando em 31/01 nao pode falhar em fevereiro.
    """
    base = datetime.date.fromisoformat(primeiro)
    datas = []
    for i in range(parcelas):
        mes = base.month - 1 + i
        ano = base.year + mes // 12
        mes = mes % 12 + 1
        ultimo_dia = [31, 29 if (ano % 4 == 0 and (ano % 100 != 0 or ano % 400 == 0)) else 28,
                      31, 30, 31, 30, 31, 31, 30, 31, 30, 31][mes - 1]
        datas.append(datetime.date(ano, mes, min(base.day, ultimo_dia)).isoformat())
    return datas


def faturar_pedido(pedido_id: int, dados: dict) -> dict:
    """
    Gera as parcelas a receber e marca o pedido como faturado.

    Tudo numa transacao: se a emissao da segunda parcela falhar, a primeira
    volta atras e o pedido continua aprovado. Pedido faturado com cobranca
    pela metade e a divergencia mais cara de achar depois.
    """
    parcelas = validators.inteiro_positivo(dados.get("parcelas", 1)) or 1
    if parcelas > MAX_PARCELAS:
        raise ErroDeNegocio(f"No maximo {MAX_PARCELAS} parcelas.")

    primeiro = (dados.get("primeiro_vencimento") or "").strip()
    if not validators.data_valida(primeiro):
        raise ErroDeNegocio("Primeiro vencimento invalido.")

    forma = (dados.get("forma_pagamento") or "Pix").strip()
    if forma not in FORMAS_DE_PAGAMENTO:
        raise ErroDeNegocio(f"Forma de pagamento deve ser uma de: {', '.join(FORMAS_DE_PAGAMENTO)}.")

    with database.conectar() as conexao:
        pedido = _exigir_pedido(conexao, pedido_id)
        if not repositorio.listar_itens(conexao, pedido_id):
            raise ErroDeNegocio("Um pedido sem itens nao pode ser faturado.")

        total = int(pedido["total_liquido_centavos"])
        if total <= 0:
            raise ErroDeNegocio("Um pedido sem valor nao pode ser faturado.")

        atualizado = _transicionar(conexao, pedido, estados.FATURADO, {
            "faturado_em": datetime.datetime.now().isoformat(timespec="seconds"),
        })

        # `ratear` garante que a soma das parcelas seja EXATAMENTE o total:
        # dividir 100,00 em 3 sem rateio explicito perde ou inventa centavo.
        valores = dinheiro.ratear(total, parcelas)
        vencimentos = _vencimentos_mensais(primeiro, parcelas)

        for indice, (centavos, vencimento) in enumerate(zip(valores, vencimentos), start=1):
            repositorio.inserir_parcela(conexao, {
                "cliente_id": pedido["cliente_id"],
                "cliente_nome": pedido["cliente_nome"],
                # Centavos exatos, do rateio ate a linha gravada. A conversao
                # para float que existia aqui desfazia o trabalho do `ratear`.
                "valor_centavos": centavos,
                "descricao": f"Pedido {pedido['numero']} - parcela {indice}/{parcelas}",
                "data_vencimento": vencimento,
                "tipo_pagamento": forma,
                "pedido_id": pedido_id,
                "parcela": indice,
                "total_parcelas": parcelas,
            })

        registrar_evento(conexao, acao="comercial.pedido.faturado", entidade="pedido",
                         entidade_id=pedido_id, valores_anteriores=pedido,
                         valores_novos=atualizado,
                         contexto_extra={"parcelas": parcelas, "total_centavos": total})

        emitidas = repositorio.parcelas_do_pedido(conexao, pedido_id)

    resultado = _pedido_para_tela(atualizado)
    # Mesmo formato que `obter_pedido` devolve. Duas formas para o mesmo campo
    # em dois endpoints e a inconsistencia que a tela paga depois.
    resultado["parcelas"] = [_parcela_para_tela(p) for p in emitidas]
    return resultado
