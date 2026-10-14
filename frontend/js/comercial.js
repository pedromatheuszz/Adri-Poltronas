
// =============================================================================
// COMERCIAL: Produtos, Pedidos e Agenda de Entregas
//
// O pedido e a espinha do modulo. Antes dele, pagamento e entrega ficavam
// pendurados direto no cliente, sem saber a que venda pertenciam.
//
// Regra que vale para as tres telas: o backend e a autoridade. Os totais, as
// situacoes validas e o rateio das parcelas vem prontos da API -- o JS soma
// apenas para o operador ver enquanto digita, e nunca decide valor.
// =============================================================================

var SITUACAO_PEDIDO = {
    rascunho:  { rotulo: 'Rascunho',  badge: 'badge-pendente'  },
    aberto:    { rotulo: 'Aberto',    badge: 'badge-pendente'  },
    aprovado:  { rotulo: 'Aprovado',  badge: 'badge-entrega'   },
    faturado:  { rotulo: 'Faturado',  badge: 'badge-recebido'  },
    cancelado: { rotulo: 'Cancelado', badge: 'badge-cancelado' }
};

// Rotulo do botao de cada transicao. A LISTA de transicoes possiveis vem do
// backend (`proximos_passos`); aqui so mora como cada uma se chama na tela.
var ACAO_PEDIDO = {
    aberto:    { rotulo: 'Abrir',    rota: 'abertura',  classe: 'btn-primary' },
    aprovado:  { rotulo: 'Aprovar',  rota: 'aprovacao', classe: 'btn-primary' },
    faturado:  { rotulo: 'Faturar',  rota: null,        classe: 'btn-primary' },
    cancelado: { rotulo: 'Cancelar', rota: 'cancelamento', classe: 'btn-perigo' }
};

var SITUACAO_ENTREGA = {
    'Pendente':     { badge: 'badge-pendente',  proxima: 'Em andamento', acao: 'Sair para entrega' },
    'Em andamento': { badge: 'badge-entrega',   proxima: 'Concluida',    acao: 'Concluir' },
    'Concluida':    { badge: 'badge-recebido',  proxima: null },
    'Cancelada':    { badge: 'badge-cancelado', proxima: null }
};

var _pedidoAberto = null;
var _cacheProdutos = [];


function _brl(valor) {
    // O backend ja manda o formatado; isto cobre o caso de vir so o inteiro.
    return valor && valor.formatado ? valor.formatado : formatarReal((valor || 0) / 100);
}

function _dataBR(iso) {
    if (!iso) return '-';
    var partes = String(iso).slice(0, 10).split('-');
    return partes.length === 3 ? partes[2] + '/' + partes[1] + '/' + partes[0] : iso;
}

function _periodoAluguel(pedido) {
    if (!pedido.data_inicio_aluguel && !pedido.data_fim_aluguel) return '—';
    return escaparHtml(pedido.data_inicio_aluguel || '??/??') + ' ate ' +
        escaparHtml(pedido.data_fim_aluguel || '??/??');
}

function _mascararDiaMes(campo) {
    var digitos = campo.value.replace(/\D/g, '').slice(0, 4);
    campo.value = digitos.length > 2 ? digitos.slice(0, 2) + '/' + digitos.slice(2) : digitos;
}

function _badgeSituacao(situacao) {
    var info = SITUACAO_PEDIDO[situacao] || { rotulo: situacao, badge: 'badge-cancelado' };
    return '<span class="' + info.badge + '">' + escaparHtml(info.rotulo) + '</span>';
}

/** Erro de dominio chega na chave `erro`, como manda o API_STANDARD. */
async function _pedirApi(url, opcoes) {
    var resposta = await fetch(url, opcoes);
    var dados = null;
    try { dados = await resposta.json(); } catch (_) {}
    if (!resposta.ok) {
        throw new Error((dados && dados.erro) || ('Falha (' + resposta.status + ')'));
    }
    return dados;
}

function _json(corpo) {
    return { method: 'POST', headers: CABECALHOS_JSON, body: JSON.stringify(corpo || {}) };
}


// --- Uma escrita de cada vez, por registro ------------------------------------
// Nenhum botao de escrita travava nada: um duplo clique, ou um Enter repetido
// enquanto a requisicao viajava, disparava duas.
//
// O backend passou a recusar a segunda -- as transicoes viraram UPDATE
// condicional a situacao atual, e a baixa de parcela idem. Isso fecha a
// duplicidade no banco, que era o risco caro. Mas resolve so metade: sem
// travar aqui, o operador leva um 409 vermelho por ter clicado duas vezes.
// Trocar uma falha silenciosa por uma confusa nao e progresso.
//
// A chave carrega o ID do registro, e nao so o nome da acao: travar "aprovar"
// inteiro impediria aprovar dois pedidos DIFERENTES em sequencia rapida, o que
// e uso legitimo. Faturamento e transicao compartilham a chave do pedido de
// proposito -- as duas mexem na mesma situacao, e disparar uma enquanto a
// outra viaja e a mesma corrida com outro nome.
var _escritasEmVoo = new Set();

function _emVoo(chave) {
    return _escritasEmVoo.has(chave);
}

function _travar(chave) {
    _escritasEmVoo.add(chave);
}

function _destravar(chave) {
    _escritasEmVoo.delete(chave);
}

async function _umaDeCadaVez(chave, tarefa) {
    if (_emVoo(chave)) return;
    _travar(chave);
    try {
        return await tarefa();
    } finally {
        // `finally`, e nao o fim do `try`: se a rede cair no meio, a acao
        // precisa voltar a ser possivel para o operador tentar de novo.
        _destravar(chave);
    }
}


// =============================================================================
// Produtos
// =============================================================================
async function carregarProdutos() {
    var busca = (document.getElementById('prodFiltroBusca') || {}).value || '';
    mostrarEsqueleto('tabelaProdutos', 5, 4);
    try {
        _cacheProdutos = await _pedirApi('/api/produtos?busca=' + encodeURIComponent(busca.trim()));
        renderizarProdutos(_cacheProdutos);
    } catch (erro) {
        renderizarProdutos([]);
        exibirToast('Erro ao carregar produtos: ' + erro.message, 'error');
    }
}

function renderizarProdutos(produtos) {
    var corpo = document.getElementById('tabelaProdutos');
    if (!corpo) return;
    if (!produtos.length) {
        corpo.innerHTML = linhaEstadoVazio(5, 'Nenhum produto no catalogo',
            'Cadastre os modelos de poltrona para poder lancar itens nos pedidos.');
        return;
    }
    corpo.innerHTML = produtos.map(function (p) {
        var descricao = escaparHtml(p.descricao);
        return '<tr>' +
            '<td><strong>' + escaparHtml(p.codigo) + '</strong></td>' +
            '<td class="col-nome" title="' + descricao + '">' + descricao + '</td>' +
            '<td>' + escaparHtml(p.unidade) + '</td>' +
            '<td class="valor">' + _brl(p.preco_venda) + '</td>' +
            '<td class="col-acoes"><div class="tabela-acoes">' +
            (['desenvolvedor', 'administrador', 'usuario'].indexOf(_perfilAtual) >= 0 ?
            '<button type="button" class="btn btn-secundario btn-sm" data-produto="' + p.id + '">Editar</button>' +
            '<button type="button" class="btn btn-perigo btn-sm" data-inativar="' + p.id + '">Inativar</button>' : '') +
            '</div></td></tr>';
    }).join('');
}

function abrirFormularioProduto(produto) {
    document.getElementById('formProduto').reset();
    document.getElementById('prodId').value = produto ? produto.id : '';
    document.getElementById('modalProdutoTitulo').textContent =
        produto ? 'Editar Produto' : 'Novo Produto';
    if (produto) {
        document.getElementById('prodCodigo').value = produto.codigo;
        document.getElementById('prodDescricao').value = produto.descricao;
        document.getElementById('prodUnidade').value = produto.unidade;
        document.getElementById('prodPreco').value =
            (produto.preco_venda_centavos / 100).toFixed(2).replace('.', ',');
        document.getElementById('prodObservacoes').value = produto.observacoes || '';
    }
    abrirModal('modalProduto');
}

async function salvarProduto(evento) {
    evento.preventDefault();
    var id = document.getElementById('prodId').value;
    var corpo = {
        codigo: document.getElementById('prodCodigo').value,
        descricao: document.getElementById('prodDescricao').value,
        unidade: document.getElementById('prodUnidade').value,
        preco_venda: document.getElementById('prodPreco').value || '0',
        observacoes: document.getElementById('prodObservacoes').value
    };
    try {
        await _pedirApi(id ? '/api/produtos/' + id : '/api/produtos',
            id ? { method: 'PUT', headers: CABECALHOS_JSON, body: JSON.stringify(corpo) }
               : _json(corpo));
        fecharModal('modalProduto');
        exibirToast(id ? 'Produto atualizado.' : 'Produto cadastrado.');
        carregarProdutos();
    } catch (erro) {
        exibirToast(erro.message, 'error');
    }
}

async function inativarProduto(produtoId) {
    var produto = _cacheProdutos.find(function (p) { return p.id === produtoId; });
    var confirmado = await confirmarAcao({
        titulo: 'Inativar produto',
        mensagem: 'O produto "' + (produto ? produto.descricao : '') + '" sai do catalogo, mas '
                + 'continua nos pedidos que ja o usaram. O codigo volta a ficar livre.',
        textoConfirmar: 'Inativar',
        icone: 'alerta',
        variante: 'atencao'
    });
    if (!confirmado) return;
    try {
        await _pedirApi('/api/produtos/' + produtoId, { method: 'DELETE', headers: CABECALHOS_JSON });
        exibirToast('Produto inativado.');
        carregarProdutos();
    } catch (erro) {
        exibirToast(erro.message, 'error');
    }
}


// =============================================================================
// Pedidos
// =============================================================================
async function carregarPedidos() {
    var busca = (document.getElementById('pedFiltroBusca') || {}).value || '';
    var situacao = (document.getElementById('pedFiltroSituacao') || {}).value || '';
    mostrarEsqueleto('tabelaPedidos', 8, 4);
    try {
        var params = new URLSearchParams();
        if (busca.trim()) params.set('busca', busca.trim());
        if (situacao) params.set('situacao', situacao);
        renderizarPedidos(await _pedirApi('/api/pedidos?' + params.toString()));
    } catch (erro) {
        renderizarPedidos([]);
        exibirToast('Erro ao carregar pedidos: ' + erro.message, 'error');
    }
}

function renderizarPedidos(pedidos) {
    var corpo = document.getElementById('tabelaPedidos');
    if (!corpo) return;
    if (!pedidos.length) {
        corpo.innerHTML = linhaEstadoVazio(8, 'Nenhum pedido encontrado',
            'Crie um pedido para registrar o que o cliente encomendou e o prazo combinado.');
        return;
    }
    corpo.innerHTML = pedidos.map(function (p) {
        var cliente = escaparHtml(p.cliente_nome || '');
        return '<tr>' +
            '<td class="col-numero"><strong>' + escaparHtml(p.numero) + '</strong></td>' +
            '<td class="col-nome" title="' + cliente + '">' + cliente + '</td>' +
            '<td class="valor">' + _dataBR(p.data_emissao) + '</td>' +
            '<td class="valor">' + _dataBR(p.data_entrega_prevista) + '</td>' +
            '<td class="valor">' + _periodoAluguel(p) + '</td>' +
            '<td class="valor">' + _brl(p.total_liquido) + '</td>' +
            '<td>' + _badgeSituacao(p.situacao) + '</td>' +
            '<td class="col-acoes"><div class="tabela-acoes">' +
            '<button type="button" class="btn btn-secundario btn-sm" data-pedido="' + p.id + '">Abrir</button>' +
            '</div></td></tr>';
    }).join('');
}

async function _preencherClientes(seletor, selecionado) {
    var alvo = document.getElementById(seletor);
    if (!alvo) return;
    try {
        var clientes = await _pedirApi(API_URL + '?busca=');
        alvo.innerHTML = '<option value="">Selecione um cliente...</option>' +
            clientes.map(function (c) {
                return '<option value="' + c.id + '"' +
                    (String(c.id) === String(selecionado) ? ' selected' : '') + '>' +
                    escaparHtml(c.nome) + '</option>';
            }).join('');
    } catch (_) {
        exibirToast('Nao foi possivel carregar os clientes.', 'error');
    }
}

async function abrirFormularioPedido(pedidoId) {
    document.getElementById('formPedido').reset();
    document.getElementById('pedId').value = pedidoId || '';
    _pedidoAberto = null;

    if (!pedidoId) {
        document.getElementById('modalPedidoTitulo').textContent = 'Novo Pedido';
        document.getElementById('pedidoSituacao').innerHTML = '';
        document.getElementById('pedidoBlocoItens').hidden = true;
        _renderizarAcoesPedido(null);
        await _preencherClientes('pedClienteId');
        abrirModal('modalPedido');
        return;
    }

    try {
        var pedido = await _pedirApi('/api/pedidos/' + pedidoId);
        _pedidoAberto = pedido;
        document.getElementById('modalPedidoTitulo').textContent = 'Pedido ' + pedido.numero;
        document.getElementById('pedidoSituacao').innerHTML = _badgeSituacao(pedido.situacao);
        document.getElementById('pedEntregaPrevista').value = pedido.data_entrega_prevista || '';
        document.getElementById('pedDataInicioAluguel').value = pedido.data_inicio_aluguel || '';
        document.getElementById('pedDataFimAluguel').value = pedido.data_fim_aluguel || '';
        document.getElementById('pedDesconto').value =
            (pedido.desconto_centavos / 100).toFixed(2).replace('.', ',');
        document.getElementById('pedFrete').value =
            (pedido.frete_centavos / 100).toFixed(2).replace('.', ',');
        document.getElementById('pedObservacoes').value = pedido.observacoes || '';
        await _preencherClientes('pedClienteId', pedido.cliente_id);

        // Campos e formulario de item so ficam ativos enquanto o pedido aceita
        // alteracao. A regra vem do backend, em `editavel`.
        _travarFormularioPedido(!pedido.editavel);
        _renderizarItens(pedido);
        _renderizarParcelas(pedido);
        _renderizarAcoesPedido(pedido);
        abrirModal('modalPedido');
    } catch (erro) {
        exibirToast(erro.message, 'error');
    }
}

function _travarFormularioPedido(travado) {
    ['pedClienteId', 'pedEntregaPrevista', 'pedDataInicioAluguel', 'pedDataFimAluguel',
        'pedDesconto', 'pedFrete', 'pedObservacoes']
        .forEach(function (id) {
            var campo = document.getElementById(id);
            if (campo) campo.disabled = travado;
        });
    document.getElementById('btnSalvarPedido').hidden = travado;
    document.getElementById('pedidoFormItem').hidden = travado;
}

function _renderizarItens(pedido) {
    document.getElementById('pedidoBlocoItens').hidden = false;
    var corpo = document.getElementById('tabelaItensPedido');
    var itens = pedido.itens || [];

    corpo.innerHTML = itens.length ? itens.map(function (i) {
        var descricao = escaparHtml(i.descricao);
        var aluguel = '';
        if (i.data_inicio_aluguel || i.data_fim_aluguel) {
            aluguel = '<br><small class="texto-secundario">Aluguel: ' +
                _dataBR(i.data_inicio_aluguel) + ' a ' + _dataBR(i.data_fim_aluguel) + '</small>';
        }
        var remover = pedido.editavel
            ? '<button type="button" class="btn btn-perigo btn-sm" data-item="' + i.id + '">Remover</button>'
            : '';
        return '<tr>' +
            '<td class="col-nome" title="' + descricao + '">' + descricao + aluguel + '</td>' +
            '<td class="centro">' + i.quantidade + '</td>' +
            '<td class="direita">' + _brl(i.preco_unitario) + '</td>' +
            '<td class="direita">' + _brl(i.total) + '</td>' +
            '<td class="col-acoes">' + remover + '</td></tr>';
    }).join('') : '<tr><td colspan="5"><div class="empty-state"><p>Nenhum item lancado.</p></div></td></tr>';

    document.getElementById('pedidoTotais').innerHTML =
        '<div><dt>Itens</dt><dd>' + _brl(pedido.total_bruto) + '</dd></div>' +
        '<div><dt>Desconto</dt><dd>- ' + _brl(pedido.desconto) + '</dd></div>' +
        '<div><dt>Frete</dt><dd>' + _brl(pedido.frete) + '</dd></div>' +
        '<div class="pedido-total-final"><dt>Total</dt><dd>' + _brl(pedido.total_liquido) + '</dd></div>';

    var produtos = _cacheProdutos.length ? _cacheProdutos : [];
    document.getElementById('itemProdutoId').innerHTML =
        '<option value="">Selecione...</option>' + produtos.map(function (p) {
            return '<option value="' + p.id + '">' + escaparHtml(p.codigo + ' - ' + p.descricao) + '</option>';
        }).join('');
}

var _ROTULO_PARCELA = {
    Recebido: 'Recebida',
    Pendente: 'Pendente',
    Cancelado: 'Cancelada'
};

/**
 * Parcelas a receber, dentro do proprio pedido.
 *
 * O bloco so aparece quando existem parcelas -- ou seja, depois do
 * faturamento. Antes disso ele nao teria o que dizer.
 *
 * `em_atraso` vem calculado do backend e NAO e o status gravado: o status diz
 * o que o operador declarou, `em_atraso` diz o que o calendario diz. Marcar
 * 'Atrasado' no banco exigiria uma rotina passando meia-noite, e ate ela rodar
 * a tela mentiria.
 */
function _renderizarParcelas(pedido) {
    var bloco = document.getElementById('pedidoBlocoParcelas');
    var corpo = document.getElementById('tabelaParcelasPedido');
    var resumo = document.getElementById('pedidoResumoParcelas');
    if (!bloco || !corpo) return;

    var parcelas = pedido.parcelas || [];
    bloco.hidden = !parcelas.length;
    if (!parcelas.length) return;

    corpo.innerHTML = parcelas.map(function (p) {
        var situacao = escaparHtml(_ROTULO_PARCELA[p.status] || p.status || '');
        if (p.em_atraso) situacao += ' <span class="badge badge-perigo">em atraso</span>';

        var acao = '';
        if (p.status === 'Pendente') {
            acao = '<button type="button" class="btn btn-sucesso btn-sm" ' +
                   'data-parcela-receber="' + p.parcela + '">Receber</button>';
        } else if (p.status === 'Recebido') {
            acao = '<button type="button" class="btn btn-secundario btn-sm" ' +
                   'data-parcela-desfazer="' + p.parcela + '">Desfazer</button>';
        }

        var quando = p.status === 'Recebido' && p.data_pagamento
            ? '<br><small>em ' + escaparHtml(_dataBR(p.data_pagamento)) + '</small>'
            : '';

        return '<tr>' +
            '<td class="centro">' + escaparHtml(String(p.parcela)) + '/' +
                escaparHtml(String(p.total_parcelas)) + '</td>' +
            '<td>' + escaparHtml(_dataBR(p.data_vencimento)) + '</td>' +
            '<td class="direita">' + _brl(p.valor) + '</td>' +
            '<td>' + situacao + quando + '</td>' +
            '<td class="col-acoes">' + acao + '</td></tr>';
    }).join('');

    var recebido = 0, aberto = 0;
    parcelas.forEach(function (p) {
        var centavos = p.valor_centavos || 0;
        if (p.status === 'Recebido') recebido += centavos;
        else if (p.status !== 'Cancelado') aberto += centavos;
    });
    // `formatarReal` e nao `_brl`: `_brl` espera o objeto {centavos, formatado}
    // que a API manda, e aqui a soma foi feita na tela.
    resumo.innerHTML =
        '<div><dt>Recebido</dt><dd>' + formatarReal(recebido / 100) + '</dd></div>' +
        '<div class="pedido-total-final"><dt>Em aberto</dt><dd>' +
            formatarReal(aberto / 100) + '</dd></div>';
}

async function _mudarStatusDaParcela(parcela, status) {
    var pedidoId = document.getElementById('pedId').value;
    if (!pedidoId) return;
    await _umaDeCadaVez('parcela:' + pedidoId + ':' + parcela, async function () {
        try {
            await _pedirApi('/api/pedidos/' + pedidoId + '/parcelas/' + parcela,
                            Object.assign(_json({ status: status }), { method: 'PATCH' }));
            exibirToast('Parcela ' + parcela + ' atualizada.');
            await abrirFormularioPedido(pedidoId);
            carregarPedidos();
        } catch (erro) {
            exibirToast(erro.message, 'error');
        }
    });
}

/**
 * Botoes de transicao montados a partir de `proximos_passos`.
 *
 * A lista vem do backend justamente para a tela nao repetir a maquina de
 * estados: se as duas divergirem, a tela oferece uma acao que a API recusa.
 */
function _renderizarAcoesPedido(pedido) {
    var area = document.getElementById('pedidoAcoes');
    var fechar = '<button type="button" class="modal-btn modal-btn-cancelar" ' +
                 'data-comando="fecharModal" data-arg="modalPedido">Fechar</button>';
    if (!pedido) { area.innerHTML = fechar; return; }

    var botoes = (pedido.proximos_passos || []).map(function (destino) {
        var acao = ACAO_PEDIDO[destino];
        if (!acao) return '';
        return '<button type="button" class="btn ' + acao.classe + '" data-transicao="' + destino +
               '">' + acao.rotulo + '</button>';
    }).join('');

    if (pedido.aceita_entrega) {
        botoes += '<button type="button" class="btn btn-secundario" data-agendar="' + pedido.id +
                  '">Agendar entrega</button>';
    }
    area.innerHTML = fechar + botoes;
}

async function salvarPedido(evento) {
    evento.preventDefault();
    var id = document.getElementById('pedId').value;
    var corpo = {
        cliente_id: parseInt(document.getElementById('pedClienteId').value, 10),
        data_entrega_prevista: document.getElementById('pedEntregaPrevista').value,
        data_inicio_aluguel: document.getElementById('pedDataInicioAluguel').value,
        data_fim_aluguel: document.getElementById('pedDataFimAluguel').value,
        desconto: document.getElementById('pedDesconto').value || '0',
        frete: document.getElementById('pedFrete').value || '0',
        observacoes: document.getElementById('pedObservacoes').value
    };
    if (!corpo.cliente_id) { exibirToast('Selecione um cliente.', 'error'); return; }
    try {
        var pedido = await _pedirApi(id ? '/api/pedidos/' + id : '/api/pedidos',
            id ? { method: 'PUT', headers: CABECALHOS_JSON, body: JSON.stringify(corpo) }
               : _json(corpo));
        exibirToast(id ? 'Pedido atualizado.' : 'Pedido ' + pedido.numero + ' criado.');
        carregarPedidos();
        await abrirFormularioPedido(pedido.id);
    } catch (erro) {
        exibirToast(erro.message, 'error');
    }
}

async function adicionarItemAoPedido() {
    var pedidoId = document.getElementById('pedId').value;
    if (!pedidoId) { exibirToast('Salve o pedido antes de lancar itens.', 'error'); return; }
    var produtoId = parseInt(document.getElementById('itemProdutoId').value, 10);
    if (!produtoId) { exibirToast('Selecione um produto.', 'error'); return; }

    var corpo = {
        produto_id: produtoId,
        quantidade: parseInt(document.getElementById('itemQuantidade').value, 10) || 1,
        descricao: document.getElementById('itemDescricao').value,
        preco_unitario: document.getElementById('itemPreco').value,
        data_inicio_aluguel: document.getElementById('itemDataInicio').value,
        data_fim_aluguel: document.getElementById('itemDataFim').value
    };
    try {
        var pedido = await _pedirApi('/api/pedidos/' + pedidoId + '/itens', _json(corpo));
        _pedidoAberto = pedido;
        document.getElementById('itemDescricao').value = '';
        document.getElementById('itemPreco').value = '';
        document.getElementById('itemQuantidade').value = '1';
        document.getElementById('itemDataInicio').value = '';
        document.getElementById('itemDataFim').value = '';
        _renderizarItens(pedido);
        carregarPedidos();
    } catch (erro) {
        exibirToast(erro.message, 'error');
    }
}

async function removerItemDoPedido(itemId) {
    var pedidoId = document.getElementById('pedId').value;
    try {
        var pedido = await _pedirApi('/api/pedidos/' + pedidoId + '/itens/' + itemId,
            { method: 'DELETE', headers: CABECALHOS_JSON });
        _pedidoAberto = pedido;
        _renderizarItens(pedido);
        carregarPedidos();
    } catch (erro) {
        exibirToast(erro.message, 'error');
    }
}

async function transicionarPedido(destino) {
    var pedidoId = document.getElementById('pedId').value;
    if (destino === 'faturado') { abrirFaturamento(); return; }

    if (destino === 'cancelado') {
        var confirmado = await confirmarAcao({
            titulo: 'Cancelar pedido',
            mensagem: 'O pedido fica registrado como cancelado e nao pode mais ser faturado.',
            textoConfirmar: 'Cancelar pedido',
            textoCancelar: 'Voltar',
            icone: 'alerta',
            variante: 'atencao'
        });
        if (!confirmado) return;
    }

    var acao = ACAO_PEDIDO[destino];
    await _umaDeCadaVez('pedido:' + pedidoId, async function () {
        try {
            await _pedirApi('/api/pedidos/' + pedidoId + '/' + acao.rota, _json({}));
            exibirToast('Pedido ' + (SITUACAO_PEDIDO[destino] || {}).rotulo.toLowerCase() + '.');
            carregarPedidos();
            await abrirFormularioPedido(pedidoId);
        } catch (erro) {
            exibirToast(erro.message, 'error');
        }
    });
}

function abrirFaturamento() {
    var pedido = _pedidoAberto;
    if (!pedido) return;
    document.getElementById('fatPedidoId').value = pedido.id;
    document.getElementById('formFaturamento').reset();
    document.getElementById('fatParcelas').value = 1;
    document.getElementById('fatPrimeiroVencimento').value = new Date().toISOString().slice(0, 10);
    document.getElementById('faturamentoResumo').textContent =
        'Pedido ' + pedido.numero + ' - ' + _brl(pedido.total_liquido);
    _atualizarAvisoFaturamento();
    abrirModal('modalFaturamento');
}

/** Diz o que vai acontecer ANTES de acontecer -- nao ha desfazer pela tela. */
function _atualizarAvisoFaturamento() {
    var parcelas = parseInt(document.getElementById('fatParcelas').value, 10) || 1;
    document.getElementById('faturamentoEfeito').textContent =
        'Vai gerar ' + parcelas + (parcelas === 1 ? ' parcela' : ' parcelas') +
        ' a receber, listadas no proprio pedido. O pedido passa a faturado e ' +
        'nao aceita mais alteracao de itens.';
}

// Reentrancia do faturamento.
//
async function faturar(evento) {
    evento.preventDefault();
    if (_emVoo('pedido:' + document.getElementById('fatPedidoId').value)) return;

    var pedidoId = document.getElementById('fatPedidoId').value;
    var corpo = {
        parcelas: parseInt(document.getElementById('fatParcelas').value, 10) || 1,
        primeiro_vencimento: document.getElementById('fatPrimeiroVencimento').value,
        forma_pagamento: document.getElementById('fatFormaPagamento').value
    };
    var botao = document.querySelector('#formFaturamento button[type="submit"]');
    var rotulo = botao ? botao.textContent : '';

    _travar('pedido:' + pedidoId);
    if (botao) { botao.disabled = true; botao.textContent = 'Faturando...'; }
    try {
        var pedido = await _pedirApi('/api/pedidos/' + pedidoId + '/faturamento', _json(corpo));
        fecharModal('modalFaturamento');
        exibirToast((pedido.parcelas || []).length + ' parcela(s) gerada(s) no pedido.');
        carregarPedidos();
        await abrirFormularioPedido(pedidoId);
    } catch (erro) {
        exibirToast(erro.message, 'error');
    } finally {
        // `finally` e nao o fim do `try`: se a rede cair no meio, o botao
        // precisa voltar a funcionar para o operador tentar de novo.
        _destravar('pedido:' + pedidoId);
        if (botao) { botao.disabled = false; botao.textContent = rotulo; }
    }
}


// =============================================================================
// Agenda de entregas
// =============================================================================
async function carregarEntregas() {
    var filtro = (document.getElementById('entFiltroStatus') || {}).value;
    var area = document.getElementById('agendaEntregas');
    if (area) area.innerHTML = '<p class="agenda-carregando">Carregando...</p>';
    try {
        var url = '/api/entregas';
        if (filtro && filtro !== 'todas') url += '?status=' + encodeURIComponent(filtro);
        var entregas = await _pedirApi(url);
        if (!filtro) {
            // "Em aberto" e o padrao: o que a equipe olha de manha.
            entregas = entregas.filter(function (e) {
                return e.status !== 'Concluida' && e.status !== 'Cancelada';
            });
        }
        renderizarAgenda(entregas);
    } catch (erro) {
        if (area) area.innerHTML = '';
        exibirToast('Erro ao carregar entregas: ' + erro.message, 'error');
    }
}

/**
 * Rotulo do bloco do dia.
 *
 * "Hoje", "Amanha" e "Atrasadas" ganham a data por extenso ao lado, porque
 * sozinhos nao dizem QUAL dia. Nos demais o titulo ja e a data -- repeti-la
 * na legenda seria redundante.
 */
function _rotuloDoDia(iso) {
    var hoje = new Date(); hoje.setHours(0, 0, 0, 0);
    var dia = new Date(iso + 'T00:00:00');
    var diferenca = Math.round((dia - hoje) / 86400000);
    if (diferenca < 0) return { titulo: 'Atrasada', classe: 'agenda-dia-atrasado', comData: true };
    if (diferenca === 0) return { titulo: 'Hoje', classe: 'agenda-dia-hoje', comData: true };
    if (diferenca === 1) return { titulo: 'Amanha', classe: 'agenda-dia-proximo', comData: true };
    return { titulo: _dataBR(iso), classe: '', comData: false };
}

function renderizarAgenda(entregas) {
    var area = document.getElementById('agendaEntregas');
    if (!area) return;
    if (!entregas.length) {
        area.innerHTML = '<div class="empty-state">' +
            '<div class="empty-state-icon" aria-hidden="true">' + ICONE_VAZIO + '</div>' +
            '<h3>Nenhuma entrega na agenda</h3>' +
            '<p>Agende a partir de um pedido aprovado ou pelo botao acima.</p></div>';
        return;
    }

    // Agrupa por dia, ordenado: e assim que a equipe consulta de manha.
    var porDia = {};
    entregas.slice().sort(function (a, b) {
        return (a.data_entrega + (a.hora_entrega || '')).localeCompare(
               b.data_entrega + (b.hora_entrega || ''));
    }).forEach(function (e) {
        (porDia[e.data_entrega] = porDia[e.data_entrega] || []).push(e);
    });

    area.innerHTML = Object.keys(porDia).sort().map(function (dia) {
        var rotulo = _rotuloDoDia(dia);
        var linhas = porDia[dia].map(function (e) {
            var info = SITUACAO_ENTREGA[e.status] || { badge: 'badge-cancelado' };
            var acoes = '';
            if (info.proxima) {
                acoes += '<button type="button" class="btn btn-secundario btn-sm" ' +
                         'data-entrega="' + e.id + '" data-para="' + info.proxima + '">' +
                         info.acao + '</button>';
            }
            if (e.status !== 'Concluida' && e.status !== 'Cancelada') {
                acoes += '<button type="button" class="btn btn-perigo btn-sm" ' +
                         'data-entrega="' + e.id + '" data-para="Cancelada">Cancelar</button>';
            }
            var pedido = e.pedido_id
                ? '<button type="button" class="elo-pedido" data-pedido="' + e.pedido_id +
                  '">Ver pedido</button>'
                : '';
            return '<li class="agenda-item">' +
                '<span class="agenda-hora">' + escaparHtml(e.hora_entrega || '--:--') + '</span>' +
                '<div class="agenda-corpo">' +
                '<strong>' + escaparHtml(e.cliente_nome || '') + '</strong>' +
                (e.descricao ? '<span class="agenda-descricao">' + escaparHtml(e.descricao) + '</span>' : '') +
                '</div>' +
                '<span class="' + info.badge + '">' + escaparHtml(e.status) + '</span>' +
                '<div class="tabela-acoes">' + pedido + acoes + '</div>' +
                '</li>';
        }).join('');
        // `rotulo.titulo` e `_dataBR(dia)` passam por `escaparHtml` como todo o
        // resto do arquivo. Eram a unica excecao a regra: 'Hoje'/'Amanha' sao
        // literais e a data vem validada como AAAA-MM-DD, entao exploracao e
        // implausivel -- mas uma linha herdada de versao anterior pode conter
        // outra coisa, e uma excecao a uma regra consistente e o lugar onde o
        // proximo defeito se instala sem ninguem notar.
        return '<section class="card agenda-dia ' + rotulo.classe + '">' +
            '<h3 class="agenda-dia-titulo">' + escaparHtml(rotulo.titulo) +
            (rotulo.comData ? '<small>' + escaparHtml(_dataBR(dia)) + '</small>' : '') +
            '<small class="agenda-contagem">' + porDia[dia].length +
            (porDia[dia].length === 1 ? ' entrega' : ' entregas') + '</small></h3>' +
            '<ul class="agenda-lista">' + linhas + '</ul></section>';
    }).join('');
}

async function abrirFormularioEntrega(pedido) {
    document.getElementById('formEntrega').reset();
    await _preencherClientes('entClienteId', pedido && pedido.cliente_id);

    var seletorPedido = document.getElementById('entPedidoId');
    try {
        var pedidos = await _pedirApi('/api/pedidos?situacao=aprovado');
        var faturados = await _pedirApi('/api/pedidos?situacao=faturado');
        seletorPedido.innerHTML = '<option value="">Sem pedido vinculado</option>' +
            pedidos.concat(faturados).map(function (p) {
                return '<option value="' + p.id + '" data-cliente="' + p.cliente_id + '"' +
                    (pedido && p.id === pedido.id ? ' selected' : '') + '>' +
                    escaparHtml(p.numero + ' - ' + p.cliente_nome) + '</option>';
            }).join('');
    } catch (_) {
        seletorPedido.innerHTML = '<option value="">Sem pedido vinculado</option>';
    }

    if (pedido && pedido.data_entrega_prevista) {
        document.getElementById('entData').value = pedido.data_entrega_prevista;
    }
    abrirModal('modalEntrega');
}

async function salvarEntrega(evento) {
    evento.preventDefault();
    var corpo = {
        cliente_id: parseInt(document.getElementById('entClienteId').value, 10),
        data_entrega: document.getElementById('entData').value,
        hora_entrega: document.getElementById('entHora').value,
        descricao: document.getElementById('entDescricao').value
    };
    var pedidoId = document.getElementById('entPedidoId').value;
    if (pedidoId) corpo.pedido_id = parseInt(pedidoId, 10);
    if (!corpo.cliente_id || !corpo.data_entrega) {
        exibirToast('Cliente e data sao obrigatorios.', 'error');
        return;
    }
    try {
        await _pedirApi('/api/entregas', _json(corpo));
        fecharModal('modalEntrega');
        exibirToast('Entrega agendada.');
        carregarEntregas();
        carregarNotificacoes();
    } catch (erro) {
        exibirToast(erro.message, 'error');
    }
}

async function mudarSituacaoEntrega(entregaId, destino) {
    await _umaDeCadaVez('entrega:' + entregaId, async function () {
        try {
            await _pedirApi('/api/entregas/' + entregaId + '/status',
                { method: 'PUT', headers: CABECALHOS_JSON, body: JSON.stringify({ status: destino }) });
            exibirToast('Entrega atualizada.');
            carregarEntregas();
            carregarNotificacoes();
        } catch (erro) {
            exibirToast(erro.message, 'error');
        }
    });
}


// =============================================================================
// Ligacao com a interface
// =============================================================================
function registrarEventosComerciais() {
    var liga = function (id, evento, funcao) {
        var elemento = document.getElementById(id);
        if (elemento) elemento.addEventListener(evento, funcao);
    };

    liga('formProduto', 'submit', salvarProduto);
    liga('formPedido', 'submit', salvarPedido);
    liga('pedDataInicioAluguel', 'input', function (evento) { _mascararDiaMes(evento.currentTarget); });
    liga('pedDataFimAluguel', 'input', function (evento) { _mascararDiaMes(evento.currentTarget); });
    liga('formFaturamento', 'submit', faturar);
    liga('formEntrega', 'submit', salvarEntrega);
    liga('fatParcelas', 'input', _atualizarAvisoFaturamento);
    liga('pedFiltroSituacao', 'change', carregarPedidos);
    liga('entFiltroStatus', 'change', carregarEntregas);

    // Busca com o mesmo atraso da tela de Clientes, para o comportamento nao
    // mudar de aba para aba.
    var atrasos = {};
    [['prodFiltroBusca', carregarProdutos], ['pedFiltroBusca', carregarPedidos]]
        .forEach(function (par) {
            liga(par[0], 'input', function () {
                clearTimeout(atrasos[par[0]]);
                atrasos[par[0]] = setTimeout(par[1], 300);
            });
        });

    // Delegacao: as linhas sao recriadas a cada render, entao o listener vive
    // no documento e nao em cada botao.
    document.addEventListener('click', function (evento) {
        var alvo = evento.target.closest('button');
        if (!alvo) return;

        if (alvo.dataset.produto) {
            var produto = _cacheProdutos.find(function (p) {
                return String(p.id) === alvo.dataset.produto;
            });
            if (produto) abrirFormularioProduto(produto);
        } else if (alvo.dataset.inativar) {
            inativarProduto(parseInt(alvo.dataset.inativar, 10));
        } else if (alvo.dataset.pedido) {
            if (!document.getElementById('aba-pedidos').classList.contains('active')) {
                trocarAba('pedidos');
            }
            abrirFormularioPedido(parseInt(alvo.dataset.pedido, 10));
        } else if (alvo.dataset.item) {
            removerItemDoPedido(parseInt(alvo.dataset.item, 10));
        } else if (alvo.dataset.transicao) {
            transicionarPedido(alvo.dataset.transicao);
        } else if (alvo.dataset.agendar) {
            fecharModal('modalPedido');
            abrirFormularioEntrega(_pedidoAberto);
        } else if (alvo.dataset.entrega) {
            mudarSituacaoEntrega(parseInt(alvo.dataset.entrega, 10), alvo.dataset.para);
        } else if (alvo.dataset.parcelaReceber) {
            _mudarStatusDaParcela(parseInt(alvo.dataset.parcelaReceber, 10), 'Recebido');
        } else if (alvo.dataset.parcelaDesfazer) {
            _mudarStatusDaParcela(parseInt(alvo.dataset.parcelaDesfazer, 10), 'Pendente');
        }
    });
}
