
// =============================================================================
// RELATORIOS -- as parcelas a receber reunidas numa tabela so.
//
// Ate aqui as parcelas so eram visiveis abrindo pedido por pedido: o
// faturamento de um mes inteiro ficava espalhado por N telas. Este modulo e
// a leitura reunida -- os totais vem PRONTOS do backend, calculados sobre as
// MESMAS linhas da tabela, porque resumo e tabela que divergem e o defeito
// que faz o operador parar de confiar em ambos.
//
// A regra do modulo comercial vale aqui: o backend e a autoridade. Nenhuma
// soma e feita na tela; o que o JS monta e apresentacao.
// =============================================================================

var ROTULO_SITUACAO_RELATORIO = {
    Pendente: 'Pendente',
    Recebido: 'Recebida',
    Cancelado: 'Cancelada'
};

var _ultimaRespostaRelatorio = null;

function _situacaoDaParcela(p) {
    var texto = ROTULO_SITUACAO_RELATORIO[p.status] || p.status || '';
    if (p.em_atraso) texto += ' <span class="badge badge-perigo">em atraso</span>';
    return texto;
}

/** Erro de dominio chega na chave `erro`, como manda o API_STANDARD. */
async function _pedirApiRelatorios(url, opcoes) {
    var resposta = await fetch(url, opcoes);
    var dados = null;
    try { dados = await resposta.json(); } catch (_) {}
    if (!resposta.ok) {
        throw new Error((dados && dados.erro) || ('Falha (' + resposta.status + ')'));
    }
    return dados;
}

function _queryDosFiltros() {
    var params = new URLSearchParams();
    var de = (document.getElementById('relDataDe') || {}).value || '';
    var ate = (document.getElementById('relDataAte') || {}).value || '';
    var situacao = (document.getElementById('relFiltroSituacao') || {}).value || '';
    if (de.trim()) params.set('de', de.trim());
    if (ate.trim()) params.set('ate', ate.trim());
    if (situacao) params.set('situacao', situacao);
    return params;
}

async function carregarRelatorios() {
    var corpo = document.getElementById('tabelaRelatorioParcelas');
    if (!corpo) return;
    mostrarEsqueleto('tabelaRelatorioParcelas', 7, 4);
    try {
        var dados = await _pedirApiRelatorios(
            '/api/relatorios/financeiro?' + _queryDosFiltros().toString());
        _ultimaRespostaRelatorio = dados;
        renderizarResumoDoRelatorio(dados.resumo);
        renderizarParcelasDoRelatorio(dados.parcelas);
    } catch (erro) {
        _ultimaRespostaRelatorio = null;
        renderizarResumoDoRelatorio(null);
        renderizarParcelasDoRelatorio([]);
        exibirToast('Erro ao carregar o relatorio: ' + erro.message, 'error');
    }
}

function renderizarResumoDoRelatorio(resumo) {
    var area = document.getElementById('relResumo');
    if (!area) return;

    if (!resumo) {
        area.innerHTML =
            '<div><dt>A receber</dt><dd>—</dd></div>' +
            '<div><dt>Em atraso</dt><dd>—</dd></div>' +
            '<div><dt>Recebido</dt><dd>—</dd></div>';
        return;
    }

    // Os valores formatados vem do backend (`dinheiro.serializar`); a tela
    // nao reimplementa moeda. As quantidades entram ao lado para o operador
    // conferir a tabela contra o resumo -- quando os dois divergem, o erro
    // salta aos olhos em vez de passar batido.
    area.innerHTML =
        '<div class="rel-resumo rel-resumo-a-receber"><dt>A receber (' + resumo.a_receber_qtd + ')</dt><dd>' +
            escaparHtml(resumo.a_receber.formatado) + '</dd></div>' +
        '<div class="rel-resumo rel-resumo-atrasado"><dt>Em atraso (' + resumo.atrasado_qtd + ')</dt><dd>' +
            escaparHtml(resumo.atrasado.formatado) + '</dd></div>' +
        '<div class="rel-resumo rel-resumo-recebido"><dt>Recebido (' + resumo.recebido_qtd + ')</dt><dd>' +
            escaparHtml(resumo.recebido.formatado) + '</dd></div>';
}

function renderizarParcelasDoRelatorio(parcelas) {
    var corpo = document.getElementById('tabelaRelatorioParcelas');
    if (!corpo) return;
    if (!parcelas.length) {
        corpo.innerHTML = linhaEstadoVazio(7, 'Nenhuma parcela para os filtros atuais',
            'Ajuste o periodo ou a situacao, ou fature um pedido para gerar parcelas.');
        return;
    }
    corpo.innerHTML = parcelas.map(function (p) {
        var pago = p.status === 'Recebido' && p.data_pagamento
            ? '<br><small>em ' + escaparHtml(_dataBRRelatorio(p.data_pagamento)) + '</small>'
            : '';
        return '<tr>' +
            '<td class="valor">' + escaparHtml(_dataBRRelatorio(p.data_vencimento)) + '</td>' +
            '<td class="col-nome">' + escaparHtml(p.cliente_nome || '') + '</td>' +
            '<td class="col-numero">' + escaparHtml(p.pedido_numero || '—') + '</td>' +
            '<td class="centro">' + (p.pedido_id
                ? escaparHtml(String(p.parcela)) + '/' + escaparHtml(String(p.total_parcelas))
                : '—') + '</td>' +
            '<td class="valor">' + _brlRelatorio(p.valor) + '</td>' +
            '<td>' + _situacaoDaParcela(p) + pago + '</td>' +
            '<td class="centro">' + escaparHtml(p.tipo_pagamento || '') + '</td>' +
            '</tr>';
    }).join('');
}

function _dataBRRelatorio(iso) {
    if (!iso) return '-';
    var partes = String(iso).slice(0, 10).split('-');
    return partes.length === 3 ? partes[2] + '/' + partes[1] + '/' + partes[0] : iso;
}

function _brlRelatorio(valor) {
    return valor && valor.formatado ? valor.formatado : formatarReal((valor || 0) / 100);
}

// --- Exportacao ---------------------------------------------------------------
// Download direto por fetch + blob, e nao navegacao: um <a href> para a rota
// levaria a JANELA inteira para a resposta do servidor (o Electron tratava
// como navegacao externa), e window.open abriria outra janela para um
// arquivo. O blob entrega o arquivo sem tirar o operador do lugar.
async function exportarRelatorioFinanceiro() {
    var botao = document.getElementById('btnExportarRelatorio');
    var rotulo = botao ? botao.textContent : '';
    if (botao) { botao.disabled = true; botao.textContent = 'Preparando...'; }
    try {
        var resposta = await fetch(
            '/api/relatorios/financeiro/exportar?' + _queryDosFiltros().toString());
        if (!resposta.ok) {
            var dados = null;
            try { dados = await resposta.json(); } catch (_) {}
            throw new Error((dados && dados.erro) || 'Falha ao exportar.');
        }
        var conteudo = await resposta.blob();

        // O nome vem do Content-Disposition do servidor; se algo der errado
        // na leitura, um nome generico ainda entrega o arquivo.
        var nome = 'relatorio_parcelas.xlsx';
        var disposicao = resposta.headers.get('Content-Disposition') || '';
        var achado = disposicao.match(/filename="?([^";]+)"?/);
        if (achado) nome = achado[1];

        var url = URL.createObjectURL(conteudo);
        var link = document.createElement('a');
        link.href = url;
        link.download = nome;
        document.body.appendChild(link);
        link.click();
        link.remove();
        URL.revokeObjectURL(url);
        exibirToast('Planilha gerada.');
    } catch (erro) {
        exibirToast(erro.message, 'error');
    } finally {
        if (botao) { botao.disabled = false; botao.textContent = rotulo; }
    }
}

// --- Ligacao com a interface --------------------------------------------------
function registrarEventosRelatorios() {
    var liga = function (id, evento, funcao) {
        var elemento = document.getElementById(id);
        if (elemento) elemento.addEventListener(evento, funcao);
    };

    liga('btnAplicarFiltrosRelatorio', 'click', carregarRelatorios);
    liga('btnExportarRelatorio', 'click', function () {
        // `_umaDeCadaVez` e do comercial.js e cobre escrita; aqui a unica
        // defesa e o proprio botao travando enquanto o arquivo prepara.
        exportarRelatorioFinanceiro();
    });
    liga('relFiltroSituacao', 'change', carregarRelatorios);
    ['relDataDe', 'relDataAte'].forEach(function (id) {
        liga(id, 'change', carregarRelatorios);
    });
}
