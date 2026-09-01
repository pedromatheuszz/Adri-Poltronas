"""Casos de uso de parceiros de negocio (clientes e fornecedores)."""
from __future__ import annotations

from backend_v2.nucleo import auditoria, documento as doc
from backend_v2.nucleo.erros import ConflitoDeEstado, NaoEncontrado, RegraDeNegocioViolada
from backend_v2.nucleo.validacao import Coletor
from backend_v2.infraestrutura.repo_comercial import RepositorioParceiros

OPCOES_ENTREGA = ('Entrega', 'Retirada')


def _validar(dados, *, parcial=False) -> dict:
    coletor = Coletor(dados)
    coletor.texto('nome', obrigatorio=not parcial, maximo=160, minimo=2, rotulo='Nome')
    coletor.texto('nome_fantasia', maximo=160)
    coletor.email('email', rotulo='E-mail')
    coletor.texto('telefone', maximo=20)
    coletor.cep('cep', rotulo='CEP')
    coletor.texto('logradouro', maximo=160)
    coletor.texto('numero', maximo=20)
    coletor.texto('complemento', maximo=80)
    coletor.texto('bairro', maximo=80)
    coletor.texto('cidade', maximo=80)
    coletor.uf('uf', rotulo='UF')
    coletor.opcao('entrega_retirada', OPCOES_ENTREGA, padrao='Entrega', rotulo='Entrega/Retirada')
    coletor.texto('observacoes', maximo=1000)
    e_cliente = coletor.booleano('e_cliente', padrao=True)
    e_fornecedor = coletor.booleano('e_fornecedor', padrao=False)
    if not e_cliente and not e_fornecedor:
        coletor.erro("O parceiro precisa ser cliente, fornecedor, ou ambos.")

    # Documento e opcional -- mas se vier, e validado de verdade. Aceitar
    # '11111111111' porque "tem 11 digitos" e o tipo de sujeira que so aparece
    # na hora de emitir nota.
    bruto = str(dados.get('documento') or '').strip()
    if bruto:
        digitos = doc.apenas_digitos(bruto)
        tipo = doc.tipo_documento(digitos)
        if tipo is None:
            coletor.erro("Documento invalido: nao e um CPF nem um CNPJ valido.")
            coletor.limpo['documento'] = ''
            coletor.limpo['tipo_documento'] = ''
        else:
            coletor.limpo['documento'] = digitos
            coletor.limpo['tipo_documento'] = tipo
    else:
        coletor.limpo['documento'] = ''
        coletor.limpo['tipo_documento'] = ''

    return coletor.validar()


def criar(unidade, dados) -> dict:
    campos = _validar(dados)
    repositorio = unidade.repositorio(RepositorioParceiros)

    if campos['documento']:
        existente = repositorio.por_documento(campos['documento'])
        if existente:
            raise ConflitoDeEstado(
                "Ja existe um parceiro ativo com o documento %s (#%d %s)."
                % (doc.formatar(campos['documento']), existente['id'], existente['nome'])
            )

    campos['e_cliente'] = 1 if campos['e_cliente'] else 0
    campos['e_fornecedor'] = 1 if campos['e_fornecedor'] else 0
    identificador = repositorio.inserir(campos)
    criado = repositorio.buscar(identificador)
    auditoria.registrar(
        unidade.conexao, acao='cadastro.parceiro.criado',
        entidade='parceiro', entidade_id=identificador, novos=criado,
    )
    return criado


def atualizar(unidade, identificador: int, dados) -> dict:
    repositorio = unidade.repositorio(RepositorioParceiros)
    anterior = repositorio.buscar_ativo(identificador)
    if not anterior:
        raise NaoEncontrado('Parceiro', identificador)

    campos = _validar(dados)
    if campos['documento']:
        outro = repositorio.por_documento(campos['documento'])
        if outro and outro['id'] != identificador:
            raise ConflitoDeEstado(
                "O documento %s ja pertence ao parceiro #%d."
                % (doc.formatar(campos['documento']), outro['id'])
            )

    campos['e_cliente'] = 1 if campos['e_cliente'] else 0
    campos['e_fornecedor'] = 1 if campos['e_fornecedor'] else 0
    repositorio.atualizar(identificador, campos)
    # Carimbo de alteracao no SQL, e nao em Python: a hora tem de vir do mesmo
    # relogio que preenche os DEFAULT do esquema.
    unidade.conexao.execute(
        "UPDATE parceiros SET atualizado_em=datetime('now', 'localtime') WHERE id=?",
        (identificador,),
    )
    novo = repositorio.buscar(identificador)
    auditoria.registrar(
        unidade.conexao, acao='cadastro.parceiro.atualizado',
        entidade='parceiro', entidade_id=identificador,
        anteriores=anterior, novos=novo,
    )
    return novo


def inativar(unidade, identificador: int) -> None:
    repositorio = unidade.repositorio(RepositorioParceiros)
    anterior = repositorio.buscar_ativo(identificador)
    if not anterior:
        raise NaoEncontrado('Parceiro', identificador)
    # Nao apaga: as FKs sao RESTRICT e o historico precisa continuar legivel.
    # Inativar preserva os documentos ja emitidos e tira o parceiro das listas.
    repositorio.inativar(identificador)
    auditoria.registrar(
        unidade.conexao, acao='cadastro.parceiro.inativado',
        entidade='parceiro', entidade_id=identificador, anteriores=anterior,
        extra={'tinha_movimento': repositorio.tem_movimento(identificador)},
    )


def obter(unidade, identificador: int) -> dict:
    parceiro = unidade.repositorio(RepositorioParceiros).buscar_ativo(identificador)
    if not parceiro:
        raise NaoEncontrado('Parceiro', identificador)
    return parceiro


def exigir_cliente(unidade, identificador: int) -> dict:
    parceiro = obter(unidade, identificador)
    if not parceiro['e_cliente']:
        raise RegraDeNegocioViolada(
            "O parceiro #%d nao esta marcado como cliente." % identificador
        )
    return parceiro


def exigir_fornecedor(unidade, identificador: int) -> dict:
    parceiro = obter(unidade, identificador)
    if not parceiro['e_fornecedor']:
        raise RegraDeNegocioViolada(
            "O parceiro #%d nao esta marcado como fornecedor." % identificador
        )
    return parceiro


def listar(unidade, *, busca='', papel='', cidade='', pagina=None):
    repositorio = unidade.repositorio(RepositorioParceiros)
    return repositorio.listar(
        busca=busca, papel=papel, cidade=cidade,
        limite=pagina.limite, deslocamento=pagina.deslocamento,
    )
