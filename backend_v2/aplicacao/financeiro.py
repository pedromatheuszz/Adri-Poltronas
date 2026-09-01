"""
Casos de uso financeiros: titulos a receber/pagar, baixas e caixa.

A situacao do titulo NUNCA e escrita: e derivada das baixas pela view
`titulos_situacao`. No v1, `status` era coluna gravavel, e um PUT sem o campo
revertia uma cobranca ja recebida -- apagando receita sem deixar rastro.
"""
from __future__ import annotations

from backend_v2.nucleo import auditoria
from backend_v2.nucleo.dinheiro import ratear
from backend_v2.nucleo.erros import ConflitoDeEstado, NaoEncontrado, RegraDeNegocioViolada
from backend_v2.nucleo.validacao import Coletor, data_valida
from backend_v2.infraestrutura.repo_documentos import RepositorioNumeracao
from backend_v2.infraestrutura.repo_financeiro import (
    RepositorioBaixas, RepositorioCaixa, RepositorioContas, RepositorioTitulos,
)
from backend_v2.aplicacao import cadastro

NATUREZAS = ('receber', 'pagar')
FORMAS = ('dinheiro', 'pix', 'boleto', 'cartao', 'transferencia', 'cheque', 'outro')


# ---------------------------------------------------------------------------
# Titulos
# ---------------------------------------------------------------------------
def emitir_titulos(
    unidade,
    *,
    natureza: str,
    parceiro_id: int,
    valor_total_centavos: int,
    vencimentos: list[str],
    descricao: str = '',
    forma_pagamento: str = 'dinheiro',
    origem_tipo: str = '',
    origem_id=None,
) -> list[dict]:
    """
    Emite N parcelas de um valor total.

    O rateio vem de `nucleo.dinheiro.ratear`: 100,00 em 3 vira 33,34 + 33,33 +
    33,33, e a soma das parcelas e EXATAMENTE o total. Dividir com float e
    arredondar cada parcela e como se perde (ou inventa) centavo.
    """
    if natureza not in NATUREZAS:
        raise RegraDeNegocioViolada("Natureza invalida: %s." % natureza)
    if valor_total_centavos <= 0:
        raise RegraDeNegocioViolada("O valor do titulo deve ser positivo.")
    if not vencimentos:
        raise RegraDeNegocioViolada("Informe ao menos um vencimento.")
    for vencimento in vencimentos:
        if not data_valida(vencimento):
            raise RegraDeNegocioViolada("Vencimento invalido: %r." % vencimento)

    repositorio = unidade.repositorio(RepositorioTitulos)
    numeracao = unidade.repositorio(RepositorioNumeracao)
    especie = 'REC' if natureza == 'receber' else 'PAG'

    valores = ratear(valor_total_centavos, len(vencimentos))
    emitidos = []
    for indice, (vencimento, valor) in enumerate(zip(vencimentos, valores), start=1):
        titulo_id = repositorio.inserir({
            'numero': numeracao.proximo(especie),
            'natureza': natureza,
            'parceiro_id': parceiro_id,
            'origem_tipo': origem_tipo,
            'origem_id': origem_id,
            'parcela': indice,
            'total_parcelas': len(vencimentos),
            'descricao': descricao,
            'valor_centavos': valor,
            'data_vencimento': vencimento,
            'forma_pagamento': forma_pagamento,
        })
        emitidos.append(repositorio.buscar(titulo_id))

    auditoria.registrar(
        unidade.conexao, acao='financeiro.titulo.emitido',
        entidade='titulo', entidade_id=emitidos[0]['id'] if emitidos else None,
        novos={
            'natureza': natureza, 'parcelas': len(vencimentos),
            'valor_total_centavos': valor_total_centavos,
            'origem_tipo': origem_tipo, 'origem_id': origem_id,
        },
    )
    return emitidos


def criar_titulo_avulso(unidade, dados) -> list[dict]:
    """Titulo sem documento de origem (despesa fixa, aporte, etc.)."""
    coletor = Coletor(dados)
    natureza = coletor.opcao('natureza', NATUREZAS, obrigatorio=True, rotulo='Natureza')
    parceiro_id = coletor.referencia('parceiro_id', rotulo='Parceiro')
    valor = coletor.dinheiro('valor', obrigatorio=True, minimo=1, rotulo='Valor')
    coletor.texto('descricao', maximo=300)
    coletor.opcao('forma_pagamento', FORMAS, padrao='dinheiro', rotulo='Forma de pagamento')
    parcelas = coletor.inteiro('parcelas', padrao=1, minimo=1, rotulo='Parcelas')
    vencimentos = coletor.lista('vencimentos', obrigatoria=False)
    primeiro = coletor.data('data_vencimento', rotulo='Vencimento')
    campos = coletor.validar()

    if not vencimentos:
        if not primeiro:
            raise RegraDeNegocioViolada(
                "Informe `vencimentos` (lista) ou `data_vencimento` para a primeira parcela."
            )
        vencimentos = _serie_mensal(primeiro, parcelas or 1)

    cadastro.obter(unidade, parceiro_id)
    return emitir_titulos(
        unidade,
        natureza=natureza,
        parceiro_id=parceiro_id,
        valor_total_centavos=valor,
        vencimentos=vencimentos,
        descricao=campos['descricao'],
        forma_pagamento=campos['forma_pagamento'],
    )


def _serie_mensal(primeiro_vencimento: str, parcelas: int) -> list[str]:
    """
    Vencimentos mensais a partir do primeiro.

    Dia 31 nao existe em todo mes: a data cai para o ultimo dia do mes alvo em
    vez de estourar. Somar 30 dias, o atalho comum, faz o vencimento andar para
    tras no calendario ao longo do ano.
    """
    from calendar import monthrange
    from datetime import date

    ano, mes, dia = (int(parte) for parte in primeiro_vencimento.split('-'))
    serie = []
    for indice in range(parcelas):
        total_meses = mes - 1 + indice
        ano_alvo = ano + total_meses // 12
        mes_alvo = total_meses % 12 + 1
        ultimo_dia = monthrange(ano_alvo, mes_alvo)[1]
        serie.append(date(ano_alvo, mes_alvo, min(dia, ultimo_dia)).isoformat())
    return serie


def cancelar_titulo(unidade, titulo_id: int, motivo: str = '') -> dict:
    repositorio = unidade.repositorio(RepositorioTitulos)
    situacao = repositorio.situacao(titulo_id)
    if not situacao:
        raise NaoEncontrado('Titulo', titulo_id)
    if situacao['cancelado']:
        raise ConflitoDeEstado("Titulo ja cancelado.")
    if situacao['baixado_centavos'] > 0:
        # Cancelar com baixa faria o dinheiro ja movimentado no caixa apontar
        # para um titulo inexistente. Estorne as baixas primeiro.
        raise ConflitoDeEstado(
            "O titulo tem baixas. Estorne as baixas antes de cancelar."
        )
    repositorio.cancelar(titulo_id, motivo)
    auditoria.registrar(
        unidade.conexao, acao='financeiro.titulo.cancelado',
        entidade='titulo', entidade_id=titulo_id,
        anteriores=situacao, extra={'motivo': motivo},
    )
    return repositorio.completo(titulo_id)


def obter_titulo(unidade, titulo_id: int) -> dict:
    titulo = unidade.repositorio(RepositorioTitulos).completo(titulo_id)
    if not titulo:
        raise NaoEncontrado('Titulo', titulo_id)
    return titulo


def listar_titulos(unidade, *, natureza='', situacao='', parceiro_id=None,
                   vence_de='', vence_ate='', pagina=None):
    return unidade.repositorio(RepositorioTitulos).listar(
        natureza=natureza, situacao=situacao, parceiro_id=parceiro_id,
        vence_de=vence_de, vence_ate=vence_ate,
        limite=pagina.limite, deslocamento=pagina.deslocamento,
    )


# ---------------------------------------------------------------------------
# Baixas
# ---------------------------------------------------------------------------
def baixar(unidade, titulo_id: int, dados) -> dict:
    """
    Registra recebimento/pagamento e move o caixa NA MESMA transacao.

    Baixa sem movimento de caixa (ou o contrario) e como o financeiro e o
    extrato divergem sem ninguem perceber -- e ninguem consegue dizer qual dos
    dois esta certo depois.
    """
    coletor = Coletor(dados)
    conta_id = coletor.referencia('conta_id', rotulo='Conta financeira')
    valor = coletor.dinheiro('valor', obrigatorio=True, minimo=1, rotulo='Valor')
    coletor.dinheiro('juros', padrao=0, minimo=0, rotulo='Juros')
    coletor.dinheiro('desconto', padrao=0, minimo=0, rotulo='Desconto')
    coletor.data('data_baixa', rotulo='Data da baixa')
    coletor.opcao('forma_pagamento', FORMAS, padrao='dinheiro', rotulo='Forma de pagamento')
    coletor.texto('observacao', maximo=300)
    campos = coletor.validar()

    titulos = unidade.repositorio(RepositorioTitulos)
    situacao = titulos.situacao(titulo_id)
    if not situacao:
        raise NaoEncontrado('Titulo', titulo_id)
    if situacao['cancelado']:
        raise ConflitoDeEstado("Nao da para baixar um titulo cancelado.")

    saldo = int(situacao['saldo_centavos'])
    if saldo <= 0:
        raise ConflitoDeEstado("Titulo ja quitado.")
    if valor > saldo:
        # Baixar acima do saldo criaria credito invisivel: o titulo ficaria
        # "mais que quitado" e a diferenca nao apareceria em lugar nenhum.
        raise RegraDeNegocioViolada(
            "Valor da baixa (%d) excede o saldo em aberto (%d) do titulo." % (valor, saldo)
        )

    contas = unidade.repositorio(RepositorioContas)
    if not contas.buscar_ativa(conta_id):
        raise NaoEncontrado('Conta financeira', conta_id)

    titulo = titulos.buscar(titulo_id)
    campos_baixa = {
        'titulo_id': titulo_id,
        'conta_id': conta_id,
        'valor_centavos': valor,
        'juros_centavos': campos['juros'],
        'desconto_centavos': campos['desconto'],
        'forma_pagamento': campos['forma_pagamento'],
        'observacao': campos['observacao'],
    }
    # A coluna so cai no DEFAULT se ficar FORA do INSERT. Mandar NULL explicito
    # nao aciona o DEFAULT do SQLite -- bate direto no NOT NULL.
    if campos['data_baixa']:
        campos_baixa['data_baixa'] = campos['data_baixa']

    baixas = unidade.repositorio(RepositorioBaixas)
    baixa_id = baixas.inserir(campos_baixa)
    # Releitura: o movimento de caixa precisa carregar exatamente a mesma data
    # da baixa, inclusive quando ela veio do DEFAULT.
    data_efetiva = baixas.buscar(baixa_id)['data_baixa']

    # Sinal no caixa: receber entra, pagar sai. Juros somam ao que entra;
    # desconto reduz. Isso e o dinheiro de verdade, nao o valor de face.
    efetivo = valor + campos['juros'] - campos['desconto']
    entrada = titulo['natureza'] == 'receber'
    unidade.repositorio(RepositorioCaixa).lancar({
        'conta_id': conta_id,
        'tipo': 'recebimento' if entrada else 'pagamento',
        'valor_centavos': efetivo if entrada else -efetivo,
        'data_movimento': data_efetiva,
        'baixa_id': baixa_id,
        'descricao': 'Baixa do titulo %s' % titulo['numero'],
    })

    auditoria.registrar(
        unidade.conexao, acao='financeiro.titulo.baixado',
        entidade='titulo', entidade_id=titulo_id,
        anteriores=situacao, novos=titulos.situacao(titulo_id),
        extra={'baixa_id': baixa_id, 'conta_id': conta_id, 'efetivo_centavos': efetivo},
    )
    return titulos.completo(titulo_id)


def estornar_baixa(unidade, baixa_id: int, motivo: str = '') -> dict:
    """Estorna a baixa e desfaz o movimento de caixa com um lancamento oposto."""
    baixas = unidade.repositorio(RepositorioBaixas)
    baixa = baixas.buscar(baixa_id)
    if not baixa:
        raise NaoEncontrado('Baixa', baixa_id)
    if baixa['estornada']:
        raise ConflitoDeEstado("Baixa ja estornada.")

    baixas.estornar(baixa_id)

    titulo = unidade.repositorio(RepositorioTitulos).buscar(baixa['titulo_id'])
    efetivo = (int(baixa['valor_centavos']) + int(baixa['juros_centavos'])
               - int(baixa['desconto_centavos']))
    entrada_original = titulo['natureza'] == 'receber'
    unidade.repositorio(RepositorioCaixa).lancar({
        'conta_id': baixa['conta_id'],
        'tipo': 'estorno',
        # Sinal invertido em relacao ao movimento original.
        'valor_centavos': -efetivo if entrada_original else efetivo,
        'baixa_id': baixa_id,
        'descricao': 'Estorno da baixa #%d%s' % (baixa_id, (' - ' + motivo) if motivo else ''),
    })
    auditoria.registrar(
        unidade.conexao, acao='financeiro.baixa.estornada',
        entidade='titulo_baixa', entidade_id=baixa_id,
        anteriores=baixa, extra={'motivo': motivo},
    )
    return unidade.repositorio(RepositorioTitulos).completo(baixa['titulo_id'])


# ---------------------------------------------------------------------------
# Contas e caixa
# ---------------------------------------------------------------------------
def criar_conta(unidade, dados) -> dict:
    coletor = Coletor(dados)
    coletor.texto('nome', obrigatorio=True, maximo=80, rotulo='Nome da conta')
    coletor.opcao('tipo', ('caixa', 'banco', 'aplicacao'), padrao='caixa', rotulo='Tipo')
    coletor.texto('banco', maximo=80)
    coletor.texto('agencia', maximo=20)
    coletor.texto('conta', maximo=30)
    coletor.dinheiro('saldo_inicial', destino='saldo_inicial_centavos',
                     padrao=0, minimo=None, rotulo='Saldo inicial')
    campos = coletor.validar()

    repositorio = unidade.repositorio(RepositorioContas)
    identificador = repositorio.inserir(campos)
    criada = repositorio.buscar(identificador)
    auditoria.registrar(
        unidade.conexao, acao='financeiro.conta.criada',
        entidade='conta_financeira', entidade_id=identificador, novos=criada,
    )
    return criada


def listar_contas(unidade) -> list[dict]:
    return unidade.repositorio(RepositorioContas).listar_com_saldo()


def extrato(unidade, *, conta_id=None, de='', ate='', pagina=None):
    return unidade.repositorio(RepositorioCaixa).extrato(
        conta_id=conta_id, de=de, ate=ate,
        limite=pagina.limite, deslocamento=pagina.deslocamento,
    )
