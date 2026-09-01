"""
Casos de uso de compra: pedido -> recebido.

Espelho do faturamento de venda, com os sinais trocados: receber ENTRA estoque
(com custo, que realimenta o custo medio) e emite titulos a PAGAR.
"""
from __future__ import annotations

from backend_v2.nucleo import auditoria
from backend_v2.nucleo.erros import ConflitoDeEstado, NaoEncontrado, RegraDeNegocioViolada
from backend_v2.nucleo.validacao import Coletor, data_valida
from backend_v2.infraestrutura.repo_comercial import RepositorioProdutos
from backend_v2.infraestrutura.repo_documentos import RepositorioCompras, RepositorioNumeracao
from backend_v2.aplicacao import cadastro, estoque as servico_estoque, financeiro

TRANSICOES = {
    'rascunho':  {'aberto', 'cancelado'},
    'aberto':    {'recebido', 'cancelado'},
    'recebido':  set(),
    'cancelado': set(),
}

SITUACOES_EDITAVEIS = ('rascunho', 'aberto')


def _exigir(unidade, documento_id: int) -> dict:
    documento = unidade.repositorio(RepositorioCompras).com_itens(documento_id)
    if not documento:
        raise NaoEncontrado('Documento de compra', documento_id)
    return documento


def _exigir_transicao(documento: dict, destino: str) -> None:
    atual = documento['situacao']
    if destino not in TRANSICOES.get(atual, set()):
        raise ConflitoDeEstado(
            "Compra %s esta em '%s' e nao pode ir para '%s'."
            % (documento['numero'], atual, destino)
        )


def _recalcular_totais(unidade, documento_id: int) -> None:
    repositorio = unidade.repositorio(RepositorioCompras)
    documento = repositorio.buscar(documento_id)
    bruto = repositorio.somar_itens(documento_id)
    liquido = bruto - int(documento['desconto_centavos']) + int(documento['frete_centavos'])
    if liquido < 0:
        raise RegraDeNegocioViolada("O desconto deixa o total da compra negativo.")
    repositorio.atualizar(documento_id, {
        'total_bruto_centavos': bruto,
        'total_liquido_centavos': liquido,
    })


def criar(unidade, dados) -> dict:
    coletor = Coletor(dados)
    parceiro_id = coletor.referencia('parceiro_id', rotulo='Fornecedor')
    coletor.data('data_prevista', rotulo='Previsao de entrega')
    coletor.dinheiro('desconto', destino='desconto_centavos',
                     padrao=0, minimo=0, rotulo='Desconto')
    coletor.dinheiro('frete', destino='frete_centavos',
                     padrao=0, minimo=0, rotulo='Frete')
    coletor.texto('condicao_pagamento', maximo=40)
    coletor.texto('observacoes', maximo=1000)
    itens = coletor.lista('itens', obrigatoria=False)
    campos = coletor.validar()

    cadastro.exigir_fornecedor(unidade, parceiro_id)

    repositorio = unidade.repositorio(RepositorioCompras)
    documento_id = repositorio.inserir({
        'numero': unidade.repositorio(RepositorioNumeracao).proximo('compra'),
        'situacao': 'rascunho',
        'parceiro_id': parceiro_id,
        'data_prevista': campos['data_prevista'],
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
        unidade.conexao, acao='compras.documento.criado',
        entidade='documento_compra', entidade_id=documento_id, novos=criado,
    )
    return criado


def _inserir_item(unidade, documento_id: int, item) -> int:
    coletor = Coletor(item if isinstance(item, dict) else {})
    produto_id = coletor.referencia('produto_id', rotulo='Produto do item')
    quantidade = coletor.inteiro('quantidade', obrigatorio=True, minimo=1, rotulo='Quantidade')
    # Na compra o preco e sempre informado: e o que o fornecedor cobrou, nao o
    # que esta no catalogo.
    preco = coletor.dinheiro('preco_unitario', obrigatorio=True, minimo=0,
                             rotulo='Preco unitario')
    coletor.validar()

    produto = unidade.repositorio(RepositorioProdutos).buscar_ativo(produto_id)
    if not produto:
        raise NaoEncontrado('Produto', produto_id)

    repositorio = unidade.repositorio(RepositorioCompras)
    return repositorio.inserir_item({
        'documento_id': documento_id,
        'produto_id': produto_id,
        'descricao': produto['descricao'],
        'quantidade': quantidade,
        'preco_unitario_centavos': preco,
        'total_centavos': preco * quantidade,
        'sequencia': repositorio.proxima_sequencia(documento_id),
    })


def adicionar_item(unidade, documento_id: int, item) -> dict:
    documento = _exigir(unidade, documento_id)
    if documento['situacao'] not in SITUACOES_EDITAVEIS:
        raise ConflitoDeEstado("Compra em '%s' nao aceita mais itens." % documento['situacao'])
    _inserir_item(unidade, documento_id, item)
    _recalcular_totais(unidade, documento_id)
    return _exigir(unidade, documento_id)


def abrir(unidade, documento_id: int) -> dict:
    documento = _exigir(unidade, documento_id)
    if not documento['itens']:
        raise RegraDeNegocioViolada("Nao da para abrir uma compra sem itens.")
    _exigir_transicao(documento, 'aberto')
    unidade.repositorio(RepositorioCompras).atualizar(documento_id, {'situacao': 'aberto'})
    auditoria.registrar(
        unidade.conexao, acao='compras.documento.aberto',
        entidade='documento_compra', entidade_id=documento_id,
    )
    return _exigir(unidade, documento_id)


def cancelar(unidade, documento_id: int, motivo: str = '') -> dict:
    documento = _exigir(unidade, documento_id)
    _exigir_transicao(documento, 'cancelado')
    unidade.repositorio(RepositorioCompras).atualizar(documento_id, {'situacao': 'cancelado'})
    unidade.conexao.execute(
        "UPDATE documentos_compra SET cancelado_em=datetime('now', 'localtime') WHERE id=?",
        (documento_id,),
    )
    auditoria.registrar(
        unidade.conexao, acao='compras.documento.cancelado',
        entidade='documento_compra', entidade_id=documento_id, extra={'motivo': motivo},
    )
    return _exigir(unidade, documento_id)


def receber(unidade, documento_id: int, dados=None) -> dict:
    """
    Recebimento: entra estoque com custo e emite titulos a pagar.

    O custo unitario do item alimenta o custo medio movel do produto -- e por
    isso que a entrada carrega valor, e a saida de venda nao.
    """
    dados = dados or {}
    documento = _exigir(unidade, documento_id)
    _exigir_transicao(documento, 'recebido')

    if not documento['itens']:
        raise RegraDeNegocioViolada("Compra sem itens nao pode ser recebida.")

    coletor = Coletor(dados)
    vencimentos = coletor.lista('vencimentos', obrigatoria=False)
    parcelas = coletor.inteiro('parcelas', padrao=1, minimo=1, rotulo='Parcelas')
    primeiro = coletor.data('primeiro_vencimento', rotulo='Primeiro vencimento')
    coletor.opcao('forma_pagamento', financeiro.FORMAS, padrao='dinheiro',
                  rotulo='Forma de pagamento')
    campos = coletor.validar()

    movimentos = []
    produtos = unidade.repositorio(RepositorioProdutos)
    for item in documento['itens']:
        produto = produtos.buscar_ativo(item['produto_id'])
        if not produto:
            raise NaoEncontrado('Produto', item['produto_id'])
        if not produto['controla_estoque']:
            continue
        movimentos.append(servico_estoque.registrar_movimento(
            unidade,
            produto_id=item['produto_id'],
            tipo='entrada_compra',
            quantidade=int(item['quantidade']),
            custo_unitario_centavos=int(item['preco_unitario_centavos']),
            origem_tipo='documento_compra',
            origem_id=documento_id,
            observacao='Recebimento da compra %s' % documento['numero'],
        ))

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
            natureza='pagar',
            parceiro_id=documento['parceiro_id'],
            valor_total_centavos=total,
            vencimentos=vencimentos,
            descricao='Compra %s' % documento['numero'],
            forma_pagamento=campos['forma_pagamento'],
            origem_tipo='documento_compra',
            origem_id=documento_id,
        )

    unidade.repositorio(RepositorioCompras).atualizar(documento_id, {'situacao': 'recebido'})
    unidade.conexao.execute(
        "UPDATE documentos_compra SET recebido_em=datetime('now', 'localtime'), "
        "atualizado_em=datetime('now', 'localtime') WHERE id=?",
        (documento_id,),
    )
    auditoria.registrar(
        unidade.conexao, acao='compras.documento.recebido',
        entidade='documento_compra', entidade_id=documento_id,
        novos={'situacao': 'recebido'},
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


def obter(unidade, documento_id: int) -> dict:
    return _exigir(unidade, documento_id)


def listar(unidade, *, situacao='', parceiro_id=None, de='', ate='', pagina=None):
    return unidade.repositorio(RepositorioCompras).listar(
        situacao=situacao, parceiro_id=parceiro_id, de=de, ate=ate,
        limite=pagina.limite, deslocamento=pagina.deslocamento,
    )
