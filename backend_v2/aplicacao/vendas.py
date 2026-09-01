"""
Casos de uso de venda: orcamento -> pedido -> faturado.

Orcamento e pedido sao o MESMO registro em situacoes diferentes. Faturar e a
transicao que produz efeito no resto do ERP: baixa estoque e emite titulos a
receber. Os tres acontecem na mesma transacao -- ou o pedido fatura inteiro,
ou nao fatura.
"""
from __future__ import annotations

from backend_v2.nucleo import auditoria
from backend_v2.nucleo.dinheiro import serializar
from backend_v2.nucleo.erros import ConflitoDeEstado, NaoEncontrado, RegraDeNegocioViolada
from backend_v2.nucleo.validacao import Coletor, data_valida
from backend_v2.infraestrutura.repo_comercial import RepositorioProdutos
from backend_v2.infraestrutura.repo_documentos import RepositorioNumeracao, RepositorioVendas
from backend_v2.aplicacao import cadastro, estoque as servico_estoque, financeiro

ESPECIES = ('orcamento', 'pedido')
SITUACOES = ('rascunho', 'aberto', 'aprovado', 'faturado', 'cancelado')

# De onde para onde um documento pode ir. Sem esta tabela, cada rota decide
# sozinha o que aceita -- e alguem acaba faturando um pedido cancelado.
TRANSICOES = {
    'rascunho':  {'aberto', 'cancelado'},
    'aberto':    {'aprovado', 'cancelado'},
    'aprovado':  {'faturado', 'cancelado'},
    'faturado':  set(),      # terminal: estoque e financeiro ja foram gerados
    'cancelado': set(),
}

SITUACOES_EDITAVEIS = ('rascunho', 'aberto')


def _exigir(unidade, documento_id: int) -> dict:
    documento = unidade.repositorio(RepositorioVendas).com_itens(documento_id)
    if not documento:
        raise NaoEncontrado('Documento de venda', documento_id)
    return documento


def _exigir_transicao(documento: dict, destino: str) -> None:
    atual = documento['situacao']
    if destino not in TRANSICOES.get(atual, set()):
        raise ConflitoDeEstado(
            "Documento %s esta em '%s' e nao pode ir para '%s'."
            % (documento['numero'], atual, destino)
        )


def _recalcular_totais(unidade, documento_id: int) -> dict:
    repositorio = unidade.repositorio(RepositorioVendas)
    documento = repositorio.buscar(documento_id)
    bruto = repositorio.somar_itens(documento_id)
    liquido = bruto - int(documento['desconto_centavos']) + int(documento['frete_centavos'])
    if liquido < 0:
        raise RegraDeNegocioViolada(
            "O desconto deixa o total do documento negativo."
        )
    repositorio.atualizar(documento_id, {
        'total_bruto_centavos': bruto,
        'total_liquido_centavos': liquido,
    })
    return repositorio.buscar(documento_id)


# ---------------------------------------------------------------------------
# Criacao e edicao
# ---------------------------------------------------------------------------
def criar(unidade, dados) -> dict:
    coletor = Coletor(dados)
    parceiro_id = coletor.referencia('parceiro_id', rotulo='Cliente')
    especie = coletor.opcao('especie', ESPECIES, padrao='pedido', rotulo='Especie')
    coletor.data('data_validade', rotulo='Validade')
    coletor.data('data_entrega_prevista', rotulo='Entrega prevista')
    coletor.dinheiro('desconto', destino='desconto_centavos',
                     padrao=0, minimo=0, rotulo='Desconto')
    coletor.dinheiro('frete', destino='frete_centavos',
                     padrao=0, minimo=0, rotulo='Frete')
    coletor.texto('condicao_pagamento', maximo=40)
    coletor.texto('observacoes', maximo=1000)
    itens = coletor.lista('itens', obrigatoria=False)
    campos = coletor.validar()

    cadastro.exigir_cliente(unidade, parceiro_id)

    repositorio = unidade.repositorio(RepositorioVendas)
    numero = unidade.repositorio(RepositorioNumeracao).proximo(especie)
    documento_id = repositorio.inserir({
        'numero': numero,
        'especie': especie,
        'situacao': 'rascunho',
        'parceiro_id': parceiro_id,
        'data_validade': campos['data_validade'],
        'data_entrega_prevista': campos['data_entrega_prevista'],
        'desconto_centavos': campos['desconto_centavos'],
        'frete_centavos': campos['frete_centavos'],
        'condicao_pagamento': campos['condicao_pagamento'] or 'a_vista',
        'observacoes': campos['observacoes'],
    })

    for item in itens:
        _inserir_item(unidade, documento_id, item)
    _recalcular_totais(unidade, documento_id)

    criado = _exigir(unidade, documento_id)
    auditoria.registrar(
        unidade.conexao, acao='vendas.documento.criado',
        entidade='documento_venda', entidade_id=documento_id, novos=criado,
    )
    return criado


def _inserir_item(unidade, documento_id: int, item) -> int:
    coletor = Coletor(item if isinstance(item, dict) else {})
    produto_id = coletor.referencia('produto_id', rotulo='Produto do item')
    quantidade = coletor.inteiro('quantidade', obrigatorio=True, minimo=1, rotulo='Quantidade')
    preco_informado = coletor.dinheiro('preco_unitario', padrao=None, minimo=0,
                                       rotulo='Preco unitario')
    desconto = coletor.dinheiro('desconto', destino='desconto_centavos',
                                padrao=0, minimo=0, rotulo='Desconto do item')
    campos = coletor.validar()

    produto = unidade.repositorio(RepositorioProdutos).buscar_ativo(produto_id)
    if not produto:
        raise NaoEncontrado('Produto', produto_id)

    # Preco do catalogo quando nao informado; mas o valor fica GRAVADO no item.
    # Mudar o preco do produto depois nao pode reescrever documento emitido.
    preco = preco_informado if preco_informado is not None else int(produto['preco_venda_centavos'])
    total = preco * quantidade - desconto
    if total < 0:
        raise RegraDeNegocioViolada(
            "O desconto do item %s excede o valor da linha." % produto['codigo']
        )

    repositorio = unidade.repositorio(RepositorioVendas)
    return repositorio.inserir_item({
        'documento_id': documento_id,
        'produto_id': produto_id,
        'descricao': produto['descricao'],
        'quantidade': quantidade,
        'preco_unitario_centavos': preco,
        'desconto_centavos': campos['desconto_centavos'],
        'total_centavos': total,
        'sequencia': repositorio.proxima_sequencia(documento_id),
    })


def adicionar_item(unidade, documento_id: int, item) -> dict:
    documento = _exigir(unidade, documento_id)
    if documento['situacao'] not in SITUACOES_EDITAVEIS:
        raise ConflitoDeEstado(
            "Documento em '%s' nao aceita mais itens." % documento['situacao']
        )
    _inserir_item(unidade, documento_id, item)
    _recalcular_totais(unidade, documento_id)
    atualizado = _exigir(unidade, documento_id)
    auditoria.registrar(
        unidade.conexao, acao='vendas.documento.item_adicionado',
        entidade='documento_venda', entidade_id=documento_id, novos=atualizado,
    )
    return atualizado


def remover_itens(unidade, documento_id: int) -> dict:
    documento = _exigir(unidade, documento_id)
    if documento['situacao'] not in SITUACOES_EDITAVEIS:
        raise ConflitoDeEstado(
            "Documento em '%s' nao pode ter itens removidos." % documento['situacao']
        )
    unidade.repositorio(RepositorioVendas).remover_itens(documento_id)
    _recalcular_totais(unidade, documento_id)
    return _exigir(unidade, documento_id)


# ---------------------------------------------------------------------------
# Transicoes
# ---------------------------------------------------------------------------
def _transicionar(unidade, documento_id: int, destino: str, campos_extra=None) -> dict:
    documento = _exigir(unidade, documento_id)
    _exigir_transicao(documento, destino)
    campos = {'situacao': destino}
    campos.update(campos_extra or {})
    unidade.repositorio(RepositorioVendas).atualizar(documento_id, campos)
    unidade.conexao.execute(
        "UPDATE documentos_venda SET atualizado_em=datetime('now', 'localtime') WHERE id=?",
        (documento_id,),
    )
    novo = _exigir(unidade, documento_id)
    auditoria.registrar(
        unidade.conexao, acao='vendas.documento.%s' % destino,
        entidade='documento_venda', entidade_id=documento_id,
        anteriores={'situacao': documento['situacao']}, novos={'situacao': destino},
    )
    return novo


def abrir(unidade, documento_id: int) -> dict:
    documento = _exigir(unidade, documento_id)
    if not documento['itens']:
        raise RegraDeNegocioViolada("Nao da para abrir um documento sem itens.")
    return _transicionar(unidade, documento_id, 'aberto')


def aprovar(unidade, documento_id: int) -> dict:
    return _transicionar(unidade, documento_id, 'aprovado')


def cancelar(unidade, documento_id: int, motivo: str = '') -> dict:
    resultado = _transicionar(unidade, documento_id, 'cancelado')
    unidade.conexao.execute(
        "UPDATE documentos_venda SET cancelado_em=datetime('now', 'localtime') WHERE id=?",
        (documento_id,),
    )
    if motivo:
        auditoria.registrar(
            unidade.conexao, acao='vendas.documento.cancelado_motivo',
            entidade='documento_venda', entidade_id=documento_id,
            extra={'motivo': motivo},
        )
    return _exigir(unidade, documento_id) if motivo else resultado


def faturar(unidade, documento_id: int, dados=None) -> dict:
    """
    Faturamento: a transicao que gera efeito real.

    1. baixa o estoque de cada item que controla saldo;
    2. emite os titulos a receber conforme as parcelas;
    3. marca o documento como faturado.

    Tudo na transacao da unidade de trabalho. Se o passo 2 falhar, o passo 1
    volta atras -- e nao fica estoque baixado sem cobranca correspondente, que
    e a divergencia mais cara de achar depois.
    """
    dados = dados or {}
    documento = _exigir(unidade, documento_id)
    _exigir_transicao(documento, 'faturado')

    if not documento['itens']:
        raise RegraDeNegocioViolada("Documento sem itens nao pode ser faturado.")

    coletor = Coletor(dados)
    vencimentos = coletor.lista('vencimentos', obrigatoria=False)
    parcelas = coletor.inteiro('parcelas', padrao=1, minimo=1, rotulo='Parcelas')
    primeiro = coletor.data('primeiro_vencimento', rotulo='Primeiro vencimento')
    coletor.opcao('forma_pagamento', financeiro.FORMAS, padrao='dinheiro',
                  rotulo='Forma de pagamento')
    campos = coletor.validar()

    # 1. Estoque
    movimentos = []
    produtos = unidade.repositorio(RepositorioProdutos)
    for item in documento['itens']:
        produto = produtos.buscar_ativo(item['produto_id'])
        if not produto:
            raise NaoEncontrado('Produto', item['produto_id'])
        if not produto['controla_estoque']:
            continue    # servico: entra no valor, nao no saldo
        movimentos.append(servico_estoque.registrar_movimento(
            unidade,
            produto_id=item['produto_id'],
            tipo='saida_venda',
            quantidade=int(item['quantidade']),
            origem_tipo='documento_venda',
            origem_id=documento_id,
            observacao='Faturamento do documento %s' % documento['numero'],
        ))

    # 2. Financeiro
    total = int(documento['total_liquido_centavos'])
    titulos = []
    if total > 0:
        if not vencimentos:
            base = primeiro or documento['data_emissao']
            if not data_valida(base):
                raise RegraDeNegocioViolada("Primeiro vencimento invalido.")
            vencimentos = financeiro._serie_mensal(base, parcelas or 1)
        titulos = financeiro.emitir_titulos(
            unidade,
            natureza='receber',
            parceiro_id=documento['parceiro_id'],
            valor_total_centavos=total,
            vencimentos=vencimentos,
            descricao='Venda %s' % documento['numero'],
            forma_pagamento=campos['forma_pagamento'],
            origem_tipo='documento_venda',
            origem_id=documento_id,
        )

    # 3. Documento
    unidade.repositorio(RepositorioVendas).atualizar(documento_id, {'situacao': 'faturado'})
    unidade.conexao.execute(
        "UPDATE documentos_venda SET faturado_em=datetime('now', 'localtime'), "
        "atualizado_em=datetime('now', 'localtime') WHERE id=?",
        (documento_id,),
    )

    auditoria.registrar(
        unidade.conexao, acao='vendas.documento.faturado',
        entidade='documento_venda', entidade_id=documento_id,
        anteriores={'situacao': documento['situacao']},
        novos={'situacao': 'faturado'},
        extra={
            'movimentos_estoque': [m['id'] for m in movimentos],
            'titulos_emitidos': [t['id'] for t in titulos],
            'total_centavos': total,
        },
    )
    resultado = _exigir(unidade, documento_id)
    resultado['titulos_emitidos'] = titulos
    resultado['movimentos_estoque'] = movimentos
    return resultado


# ---------------------------------------------------------------------------
# Consulta
# ---------------------------------------------------------------------------
def obter(unidade, documento_id: int) -> dict:
    return _exigir(unidade, documento_id)


def listar(unidade, *, situacao='', especie='', parceiro_id=None, de='', ate='', pagina=None):
    return unidade.repositorio(RepositorioVendas).listar(
        situacao=situacao, especie=especie, parceiro_id=parceiro_id, de=de, ate=ate,
        limite=pagina.limite, deslocamento=pagina.deslocamento,
    )


def serializar_documento(documento: dict) -> dict:
    """Acrescenta os valores formatados sem tirar os inteiros."""
    saida = dict(documento)
    for campo in ('total_bruto_centavos', 'desconto_centavos',
                  'frete_centavos', 'total_liquido_centavos'):
        if campo in saida:
            saida[campo.replace('_centavos', '')] = serializar(saida[campo])
    for item in saida.get('itens', []) or []:
        for campo in ('preco_unitario_centavos', 'desconto_centavos', 'total_centavos'):
            if campo in item:
                item[campo.replace('_centavos', '')] = serializar(item[campo])
    return saida
