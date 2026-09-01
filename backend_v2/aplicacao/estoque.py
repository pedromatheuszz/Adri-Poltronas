"""
Casos de uso de estoque.

Toda alteracao de saldo passa por aqui. Nenhum outro modulo escreve em
`estoque_movimentos` direto: vendas e compras CHAMAM estas funcoes. E o que
mantem a regra de saldo negativo e o custo medio num lugar so.
"""
from __future__ import annotations

from backend_v2.nucleo import auditoria
from backend_v2.nucleo.erros import ConflitoDeEstado, NaoEncontrado, RegraDeNegocioViolada
from backend_v2.nucleo.validacao import Coletor
from backend_v2.infraestrutura.repo_comercial import RepositorioEstoque, RepositorioProdutos

TIPOS_ENTRADA = ('entrada_compra', 'ajuste_positivo', 'inventario')
TIPOS_SAIDA = ('saida_venda', 'ajuste_negativo')


def _exigir_produto(unidade, produto_id: int) -> dict:
    produto = unidade.repositorio(RepositorioProdutos).buscar_ativo(produto_id)
    if not produto:
        raise NaoEncontrado('Produto', produto_id)
    return produto


def registrar_movimento(
    unidade,
    *,
    produto_id: int,
    tipo: str,
    quantidade: int,
    custo_unitario_centavos: int = 0,
    origem_tipo: str = '',
    origem_id=None,
    observacao: str = '',
    permitir_negativo: bool = False,
) -> dict:
    """
    Grava um movimento. `quantidade` e sempre POSITIVA aqui; o sinal sai do
    `tipo`. Deixar quem chama escolher o sinal seria pedir para alguem inverter
    uma saida em entrada por engano.
    """
    produto = _exigir_produto(unidade, produto_id)
    if quantidade <= 0:
        raise RegraDeNegocioViolada("A quantidade do movimento deve ser positiva.")

    if not produto['controla_estoque']:
        raise RegraDeNegocioViolada(
            "O produto %s nao controla estoque (e servico)." % produto['codigo']
        )

    repositorio = unidade.repositorio(RepositorioEstoque)
    saldo_antes = repositorio.saldo(produto_id)

    if tipo in TIPOS_SAIDA:
        assinada = -abs(quantidade)
    elif tipo in TIPOS_ENTRADA:
        assinada = abs(quantidade)
    else:
        raise RegraDeNegocioViolada("Tipo de movimento invalido: %s." % tipo)

    saldo_depois = saldo_antes + assinada
    if saldo_depois < 0 and not permitir_negativo:
        # Estoque negativo e quase sempre erro de lancamento, nao realidade.
        # A excecao (`permitir_negativo`) existe para carga inicial e acerto de
        # inventario, onde a divergencia ja aconteceu no mundo fisico.
        raise RegraDeNegocioViolada(
            "Saldo insuficiente para %s: ha %d em estoque e a saida e de %d."
            % (produto['codigo'], saldo_antes, abs(assinada))
        )

    movimento_id = repositorio.movimentar({
        'produto_id': produto_id,
        'tipo': tipo,
        'quantidade': assinada,
        'custo_unitario_centavos': int(custo_unitario_centavos or 0),
        'origem_tipo': origem_tipo,
        'origem_id': origem_id,
        'observacao': observacao,
    })

    # Custo medio movel, e so na ENTRADA com custo informado. Recalcular na
    # saida distorceria o custo: vender nao muda quanto o item custou.
    if assinada > 0 and custo_unitario_centavos:
        _recalcular_custo_medio(unidade, produto, saldo_antes, assinada, custo_unitario_centavos)

    auditoria.registrar(
        unidade.conexao, acao='estoque.movimento.registrado',
        entidade='estoque_movimento', entidade_id=movimento_id,
        novos={
            'produto_id': produto_id, 'tipo': tipo, 'quantidade': assinada,
            'saldo_antes': saldo_antes, 'saldo_depois': saldo_depois,
            'origem_tipo': origem_tipo, 'origem_id': origem_id,
        },
    )
    return {
        'id': movimento_id, 'produto_id': produto_id, 'tipo': tipo,
        'quantidade': assinada, 'saldo_antes': saldo_antes, 'saldo_depois': saldo_depois,
    }


def _recalcular_custo_medio(unidade, produto, saldo_antes, entrada, custo_entrada) -> None:
    """
    Custo medio movel ponderado.

    Com saldo anterior <= 0 o custo antigo nao tem peso: nao ha quantidade
    sobre a qual media-lo, e o custo da entrada vira o novo custo. Ponderar
    contra saldo negativo produziria custo negativo.
    """
    if saldo_antes <= 0:
        novo_custo = int(custo_entrada)
    else:
        valor_antigo = saldo_antes * int(produto['custo_medio_centavos'])
        valor_novo = entrada * int(custo_entrada)
        novo_custo = round((valor_antigo + valor_novo) / (saldo_antes + entrada))
    unidade.repositorio(RepositorioProdutos).atualizar_custo_medio(produto['id'], novo_custo)


def estornar_movimento(unidade, movimento_id: int, motivo: str = '') -> dict:
    """
    Estorno NAO apaga nem edita: grava um movimento de sinal oposto apontando
    para o original. A razao continua sendo a historia completa.
    """
    repositorio = unidade.repositorio(RepositorioEstoque)
    original = repositorio.buscar(movimento_id)
    if not original:
        raise NaoEncontrado('Movimento de estoque', movimento_id)
    if original['movimento_estornado_id']:
        raise ConflitoDeEstado("Este lancamento ja e um estorno.")
    if repositorio.ja_estornado(movimento_id):
        raise ConflitoDeEstado("Movimento #%d ja foi estornado." % movimento_id)

    novo_id = repositorio.movimentar({
        'produto_id': original['produto_id'],
        'tipo': 'estorno',
        'quantidade': -int(original['quantidade']),
        'custo_unitario_centavos': original['custo_unitario_centavos'],
        'origem_tipo': original['origem_tipo'],
        'origem_id': original['origem_id'],
        'movimento_estornado_id': movimento_id,
        'observacao': motivo or ('Estorno do movimento #%d' % movimento_id),
    })
    auditoria.registrar(
        unidade.conexao, acao='estoque.movimento.estornado',
        entidade='estoque_movimento', entidade_id=novo_id,
        anteriores=original, extra={'motivo': motivo},
    )
    return repositorio.buscar(novo_id)


def ajustar(unidade, dados) -> dict:
    """Ajuste manual de inventario."""
    coletor = Coletor(dados)
    produto_id = coletor.referencia('produto_id', rotulo='Produto')
    quantidade = coletor.inteiro('quantidade', obrigatorio=True, rotulo='Quantidade')
    coletor.texto('observacao', obrigatorio=True, maximo=300, rotulo='Motivo do ajuste')
    campos = coletor.validar()

    if quantidade == 0:
        raise RegraDeNegocioViolada("Ajuste de zero nao altera nada.")

    tipo = 'ajuste_positivo' if quantidade > 0 else 'ajuste_negativo'
    return registrar_movimento(
        unidade,
        produto_id=produto_id,
        tipo=tipo,
        quantidade=abs(quantidade),
        observacao=campos['observacao'],
        # Ajuste e onde a divergencia fisica e reconhecida; barrar negativo
        # aqui impediria justamente a correcao.
        permitir_negativo=True,
    )


def saldo(unidade, produto_id: int) -> dict:
    produto = _exigir_produto(unidade, produto_id)
    atual = unidade.repositorio(RepositorioEstoque).saldo(produto_id)
    return {
        'produto_id': produto_id,
        'codigo': produto['codigo'],
        'descricao': produto['descricao'],
        'saldo': atual,
        'estoque_minimo': produto['estoque_minimo'],
        'abaixo_do_minimo': atual <= produto['estoque_minimo'],
    }


def listar_saldos(unidade, *, apenas_abaixo_do_minimo=False, pagina=None):
    return unidade.repositorio(RepositorioEstoque).saldos(
        apenas_abaixo_do_minimo=apenas_abaixo_do_minimo,
        limite=pagina.limite, deslocamento=pagina.deslocamento,
    )


def historico(unidade, produto_id: int, *, pagina=None):
    _exigir_produto(unidade, produto_id)
    return unidade.repositorio(RepositorioEstoque).historico(
        produto_id, limite=pagina.limite, deslocamento=pagina.deslocamento,
    )
