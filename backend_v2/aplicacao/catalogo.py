"""Casos de uso de produtos."""
from __future__ import annotations

from backend_v2.nucleo import auditoria
from backend_v2.nucleo.erros import ConflitoDeEstado, NaoEncontrado
from backend_v2.nucleo.validacao import Coletor
from backend_v2.infraestrutura.repo_comercial import RepositorioEstoque, RepositorioProdutos

UNIDADES = ('UN', 'PC', 'CJ', 'M', 'M2', 'KG', 'CX', 'HR')


def _validar(dados) -> dict:
    coletor = Coletor(dados)
    coletor.texto('codigo', obrigatorio=True, maximo=40, rotulo='Codigo')
    coletor.texto('descricao', obrigatorio=True, maximo=200, minimo=2, rotulo='Descricao')
    coletor.opcao('unidade', UNIDADES, padrao='UN', rotulo='Unidade')
    coletor.dinheiro('preco_venda', destino='preco_venda_centavos',
                     padrao=0, minimo=0, rotulo='Preco de venda')
    coletor.booleano('controla_estoque', padrao=True)
    coletor.inteiro('estoque_minimo', padrao=0, minimo=0, rotulo='Estoque minimo')
    return coletor.validar()


def criar(unidade, dados) -> dict:
    campos = _validar(dados)
    repositorio = unidade.repositorio(RepositorioProdutos)

    if repositorio.por_codigo(campos['codigo']):
        raise ConflitoDeEstado("Ja existe um produto ativo com o codigo %s." % campos['codigo'])

    campos['controla_estoque'] = 1 if campos['controla_estoque'] else 0
    identificador = repositorio.inserir(campos)
    criado = repositorio.buscar(identificador)
    auditoria.registrar(
        unidade.conexao, acao='catalogo.produto.criado',
        entidade='produto', entidade_id=identificador, novos=criado,
    )
    return criado


def atualizar(unidade, identificador: int, dados) -> dict:
    repositorio = unidade.repositorio(RepositorioProdutos)
    anterior = repositorio.buscar_ativo(identificador)
    if not anterior:
        raise NaoEncontrado('Produto', identificador)

    campos = _validar(dados)
    outro = repositorio.por_codigo(campos['codigo'])
    if outro and outro['id'] != identificador:
        raise ConflitoDeEstado("O codigo %s ja pertence ao produto #%d."
                               % (campos['codigo'], outro['id']))

    # Desligar o controle de estoque de um produto que ja tem movimento
    # esconderia o saldo existente sem zera-lo -- o item sumiria da view de
    # saldos carregando quantidade.
    if anterior['controla_estoque'] and not campos['controla_estoque']:
        saldo = unidade.repositorio(RepositorioEstoque).saldo(identificador)
        if saldo != 0:
            raise ConflitoDeEstado(
                "Nao da para desligar o controle de estoque com saldo %d em aberto. "
                "Zere o saldo por ajuste antes." % saldo
            )

    campos['controla_estoque'] = 1 if campos['controla_estoque'] else 0
    repositorio.atualizar(identificador, campos)
    unidade.conexao.execute(
        "UPDATE produtos SET atualizado_em=datetime('now', 'localtime') WHERE id=?",
        (identificador,),
    )
    novo = repositorio.buscar(identificador)
    auditoria.registrar(
        unidade.conexao, acao='catalogo.produto.atualizado',
        entidade='produto', entidade_id=identificador,
        anteriores=anterior, novos=novo,
    )
    return novo


def inativar(unidade, identificador: int) -> None:
    repositorio = unidade.repositorio(RepositorioProdutos)
    anterior = repositorio.buscar_ativo(identificador)
    if not anterior:
        raise NaoEncontrado('Produto', identificador)
    saldo = unidade.repositorio(RepositorioEstoque).saldo(identificador)
    if saldo != 0:
        raise ConflitoDeEstado(
            "O produto ainda tem saldo de %d em estoque. Zere por ajuste antes de inativar."
            % saldo
        )
    repositorio.inativar(identificador)
    auditoria.registrar(
        unidade.conexao, acao='catalogo.produto.inativado',
        entidade='produto', entidade_id=identificador, anteriores=anterior,
    )


def obter(unidade, identificador: int) -> dict:
    produto = unidade.repositorio(RepositorioProdutos).buscar_ativo(identificador)
    if not produto:
        raise NaoEncontrado('Produto', identificador)
    return produto


def listar(unidade, *, busca='', apenas_estocaveis=False, pagina=None):
    return unidade.repositorio(RepositorioProdutos).listar(
        busca=busca, apenas_estocaveis=apenas_estocaveis,
        limite=pagina.limite, deslocamento=pagina.deslocamento,
    )
