"""Rotas de painel, fluxo de caixa, curva ABC e entregas."""
from __future__ import annotations

from flask import Blueprint

from backend_v2.aplicacao import relatorios
from backend_v2.nucleo.erros import NaoEncontrado, RegraDeNegocioViolada
from backend_v2.nucleo.validacao import Coletor
from backend_v2.infraestrutura.repo_comercial import RepositorioParceiros
from backend_v2.infraestrutura.repo_financeiro import RepositorioEntregas
from backend_v2.nucleo import auditoria
from .comum import argumento, corpo, ok, pagina, paginado, transacional

bp_gestao = Blueprint('gestao', __name__, url_prefix='/api/v2')

SITUACOES_ENTREGA = ('pendente', 'em_rota', 'concluida', 'cancelada')
SITUACOES_ENCERRADAS = ('concluida', 'cancelada')


@bp_gestao.get('/painel')
@transacional
def painel(u):
    return ok(relatorios.painel(u))


@bp_gestao.get('/fluxo-caixa')
@transacional
def fluxo_caixa(u):
    try:
        dias = int(argumento('dias', '30'))
    except ValueError:
        dias = 30
    return ok(relatorios.fluxo_de_caixa(u, dias=max(1, min(dias, 365))))


@bp_gestao.get('/curva-abc')
@transacional
def curva_abc(u):
    try:
        limite = int(argumento('limite', '20'))
    except ValueError:
        limite = 20
    return ok({"itens": relatorios.curva_abc(u, limite=max(1, min(limite, 200)))})


@bp_gestao.get('/entregas')
@transacional
def listar_entregas(u):
    pag = pagina()
    return paginado(
        u.repositorio(RepositorioEntregas).listar(
            situacao=argumento('situacao'), de=argumento('de'), ate=argumento('ate'),
            limite=pag.limite, deslocamento=pag.deslocamento),
        pag,
    )


@bp_gestao.post('/entregas')
@transacional
def criar_entrega(u):
    coletor = Coletor(corpo())
    parceiro_id = coletor.referencia('parceiro_id', rotulo='Cliente')
    coletor.data('data_prevista', obrigatorio=True, rotulo='Data prevista')
    coletor.hora('hora_prevista', rotulo='Hora prevista')
    coletor.texto('endereco', maximo=250)
    coletor.texto('descricao', maximo=500)
    campos = coletor.validar()

    # O endereco vem do cadastro quando nao informado. No v1 o NOME do cliente
    # vinha do corpo da requisicao, e dava para agendar para o cliente 7
    # gravando o nome de outro -- a notificacao avisava a pessoa errada.
    parceiro = u.repositorio(RepositorioParceiros).buscar_ativo(parceiro_id)
    if not parceiro:
        raise NaoEncontrado('Parceiro', parceiro_id)
    if not campos['endereco']:
        campos['endereco'] = ', '.join(parte for parte in (
            parceiro['logradouro'], parceiro['numero'],
            parceiro['bairro'], parceiro['cidade']) if parte)

    repositorio = u.repositorio(RepositorioEntregas)
    identificador = repositorio.inserir(campos)
    criada = repositorio.buscar(identificador)
    auditoria.registrar(u.conexao, acao='operacional.entrega.agendada',
                        entidade='entrega', entidade_id=identificador, novos=criada)
    return ok(criada, 201)


@bp_gestao.put('/entregas/<int:identificador>/situacao')
@transacional
def alterar_situacao_entrega(u, identificador):
    repositorio = u.repositorio(RepositorioEntregas)
    entrega = repositorio.buscar(identificador)
    if not entrega:
        raise NaoEncontrado('Entrega', identificador)

    coletor = Coletor(corpo())
    nova = coletor.opcao('situacao', SITUACOES_ENTREGA, obrigatorio=True, rotulo='Situacao')
    coletor.validar()

    if entrega['situacao'] in SITUACOES_ENCERRADAS:
        raise RegraDeNegocioViolada(
            "Entrega ja esta '%s' e nao muda mais de situacao." % entrega['situacao'])

    campos = {'situacao': nova}
    repositorio.atualizar(identificador, campos)
    if nova == 'concluida':
        u.conexao.execute(
            "UPDATE entregas SET concluida_em=datetime('now','localtime') WHERE id=?",
            (identificador,))
    atualizada = repositorio.buscar(identificador)
    auditoria.registrar(u.conexao, acao='operacional.entrega.situacao_alterada',
                        entidade='entrega', entidade_id=identificador,
                        anteriores=entrega, novos=atualizada)
    return ok(atualizada)
