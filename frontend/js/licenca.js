// =============================================================================
// LICENCA DE USO -- painel de bloqueio, teste e pagamento.
//
// Vive em arquivo proprio porque e um subsistema: telas, timers e chamadas
// de API que so existem por causa da licenca. O app.js o chama em tres
// pontos (o gancho de 402 no fetch, o boot e o painel do desenvolvedor); o
// resto do aplicativo nao sabe que ele existe.
//
// Toda chamada cruzada e em TEMPO DE EXECUCAO: nada aqui roda antes do
// DOMContentLoaded, e os scripts classicos terminam de carregar antes
// dele. Os helpers compartilhados (escaparHtml, exibirToast, CABECALHOS_JSON,
// _perfilAtual, trocarAba...) vem do app.js e seguem no ar quando qualquer
// funcao daqui e chamada.
// =============================================================================

// -----------------------------------------------------------------------------
// Licenca de uso
//
// Trinta dias de teste a partir da primeira abertura; depois, licenca paga.
// O bloqueio de verdade e do backend (`_exigir_licenca`, que responde 402); o
// que existe aqui e a tela que explica e o caminho para resolver.
//
// O pagamento e verificado PERGUNTANDO ao Mercado Pago, e nao esperando
// webhook: o backend escuta em loopback e um servidor da internet nao alcanca
// este endereco -- nao ha para onde o Mercado Pago chamar de volta.
// -----------------------------------------------------------------------------
var _licencaVencida = false;
var _intervaloDaLicenca = null;

// A cada quanto tempo se pergunta ao Mercado Pago enquanto o Pix esta na tela.
// Cinco segundos e o intervalo em que um Pix pago "cai" na hora do ponto de
// vista de quem esta olhando para o celular; menos que isso so gasta chamada.
var INTERVALO_VERIFICACAO_LICENCA_MS = 5000;

function _formatarReais(centavos) {
    var valor = (Number(centavos) || 0) / 100;
    var partes = valor.toFixed(2).split('.');
    var inteiro = partes[0];
    var agrupado = '';
    while (inteiro.length > 3) {
        agrupado = '.' + inteiro.slice(-3) + agrupado;
        inteiro = inteiro.slice(0, -3);
    }
    return 'R$ ' + inteiro + agrupado + ',' + partes[1];
}

function mostrarPainelLicenca(situacao) {
    var painel = document.getElementById('painelLicenca');
    var telaPagamento = document.getElementById('telaPagamento');
    var casca = document.getElementById('appShell');
    var eDesenvolvedor = _perfilAtual === 'desenvolvedor';
    if (!eDesenvolvedor) {
        if (painel) painel.hidden = true;
        if (telaPagamento) {
            telaPagamento.hidden = false;
            document.getElementById('tituloPagamentoNecessario').focus();
        }
        if (casca) casca.inert = true;
        return;
    }
    if (telaPagamento) telaPagamento.hidden = true;
    var titulo = document.getElementById('licencaTitulo');
    var texto = document.getElementById('licencaMensagem');
    var valor = document.getElementById('licencaValor');
    var nota = document.getElementById('licencaNota');
    var acao = document.getElementById('licencaAcao');
    if (painel) painel.hidden = false;
    if (casca) casca.classList.add('licenca-vencida');
    if (titulo) titulo.textContent = 'Seu período de teste terminou';
    if (texto) texto.textContent = 'Você pode ativar a licença desta instalação.';
    if (valor) {
        valor.hidden = false;
        if (situacao && situacao.valor_centavos) {
            valor.textContent = _formatarReais(situacao.valor_centavos);
        }
    }
    if (nota) nota.hidden = false;
    if (acao) acao.hidden = false;
}

function esconderPainelLicenca() {
    var painel = document.getElementById('painelLicenca');
    var telaPagamento = document.getElementById('telaPagamento');
    var casca = document.getElementById('appShell');
    if (painel) painel.hidden = true;
    if (telaPagamento) telaPagamento.hidden = true;
    if (casca) casca.inert = false;
    if (casca) casca.classList.remove('licenca-vencida');
}

function registrarLicencaVencida(situacao) {
    if (_licencaVencida) return;
    _licencaVencida = true;
    _dadosJaCarregados = false;
    mostrarPainelLicenca(situacao);
    if (_perfilAtual === 'desenvolvedor') trocarAba('desenvolvedor');
    // Ha cobranca aberta de uma execucao anterior? Entao ja se comeca
    // perguntando, sem pedir ao operador que refaca algo que ele ja fez.
    if (_perfilAtual === 'desenvolvedor') verificarPagamentoDaLicenca(true);
}

function registrarLicencaLiberada() {
    if (!_licencaVencida) return;
    _licencaVencida = false;
    esconderPainelLicenca();
    pararVerificacaoDaLicenca();
    liberarDadosSeOsPortoesAbrirem();
}

function atualizarAvisoDeTeste(situacao) {
    var aviso = document.getElementById('avisoTeste');
    if (!aviso) return;
    if (!situacao || situacao.estado !== 'teste') { aviso.hidden = true; return; }

    var dias = situacao.dias_restantes;
    aviso.hidden = false;
    aviso.textContent = dias === 1
        ? 'Ultimo dia do periodo de teste.'
        : 'Periodo de teste: ' + dias + ' dias restantes.';
    // Urgencia so na ultima semana. Avisar com o mesmo peso durante 30 dias
    // ensina o operador a nao ver o aviso.
    aviso.classList.toggle('urgente', dias <= 7);
}

// A versao exata vai no `title` do selo, e nao no texto: o selo precisa caber
// ao lado da marca, e "BETA" cabe. Quem quiser o numero passa o mouse.
//
// O valor vem de /api/health, que o le do package.json -- entao existe UM
// lugar onde a versao e escrita, e o selo nao pode discordar dele.
async function marcarVersaoBeta() {
    var selo = document.getElementById('seloBeta');
    if (!selo) return;
    try {
        var resp = await fetch('/api/health');
        if (!resp.ok) return;
        var versao = (await resp.json()).versao || '';
        if (versao) selo.title = 'Versao ' + versao;
    } catch (_) {
        // Sem backend o selo fica com o texto padrao. Nao vale um aviso: a
        // ausencia de backend ja tem tratamento proprio e mais visivel.
    }
}


async function checarLicenca() {
    try {
        var resp = await fetch('/api/licenca/status');
        if (!resp.ok) return null;
        var situacao = await resp.json();

        _licencaVerificada = true;
        if (situacao.estado === 'expirada') registrarLicencaVencida(situacao);
        else registrarLicencaLiberada();

        atualizarAvisoDeTeste(situacao);
        return situacao;
    } catch (_) {
        // Backend fora do ar e outro assunto, ja coberto pelo painel de conexao.
        return null;
    }
}

async function gerarPixDaLicenca() {
    if (_perfilAtual !== 'desenvolvedor') return;
    var botao = document.getElementById('btnGerarPixLicenca');
    var caixa = document.getElementById('licencaCobranca');
    if (botao) { botao.disabled = true; botao.textContent = 'Gerando...'; }

    try {
        var resp = await fetch('/api/licenca/cobranca', {
            method: 'POST', headers: CABECALHOS_JSON, body: JSON.stringify({})
        });
        var dados = await resp.json();
        if (!resp.ok) {
            _avisarNaCaixaDaLicenca(dados.erro || 'Nao foi possivel gerar a cobranca.');
            return;
        }
        _desenharCobrancaDaLicenca(dados);
        iniciarVerificacaoDaLicenca();
    } catch (_) {
        _avisarNaCaixaDaLicenca('Sem conexao para gerar a cobranca.');
    } finally {
        if (botao) { botao.disabled = false; botao.textContent = 'Pagar com Pix'; }
    }
}

function _avisarNaCaixaDaLicenca(mensagem) {
    var caixa = document.getElementById('licencaCobranca');
    if (!caixa) return;
    caixa.hidden = false;
    caixa.innerHTML = '<p class="licenca-aguardando">' + escaparHtml(mensagem) + '</p>';
}

function _desenharCobrancaDaLicenca(dados) {
    var caixa = document.getElementById('licencaCobranca');
    if (!caixa) return;

    // O base64 do QR passa por `base64Seguro` antes de virar `src`, e o
    // payload por `escaparHtml`: os dois vem de resposta HTTP externa.
    var qr = base64Seguro(dados.pix_qr_code);
    var payload = dados.pix_payload || '';

    caixa.hidden = false;
    caixa.innerHTML =
        (qr ? '<img src="data:image/png;base64,' + qr + '" alt="QR Code do Pix da licenca">' : '') +
        (payload ? '<div class="licenca-payload" id="licencaPayload">' + escaparHtml(payload) + '</div>' : '') +
        (payload ? '<button type="button" class="btn btn-secundario" data-comando="copiarPixDaLicenca">Copiar Copia e Cola</button>' : '') +
        '<p class="licenca-aguardando">Aguardando o pagamento. A tela libera sozinha assim que o Mercado Pago confirmar.</p>';
}

async function copiarPixDaLicenca() {
    var el = document.getElementById('licencaPayload');
    if (el && navigator.clipboard) {
        try {
            await navigator.clipboard.writeText(el.textContent);
            exibirToast('Copia e Cola copiado!');
        } catch (_) { exibirToast('Falha ao copiar.', 'error'); }
    }
}

function iniciarVerificacaoDaLicenca() {
    if (_perfilAtual !== 'desenvolvedor') return;
    if (_intervaloDaLicenca) return;
    _intervaloDaLicenca = setInterval(function() {
        verificarPagamentoDaLicenca(false);
    }, INTERVALO_VERIFICACAO_LICENCA_MS);
}

function pararVerificacaoDaLicenca() {
    if (!_intervaloDaLicenca) return;
    clearInterval(_intervaloDaLicenca);
    _intervaloDaLicenca = null;
}

async function verificarPagamentoDaLicenca(primeira) {
    if (_perfilAtual !== 'desenvolvedor') {
        pararVerificacaoDaLicenca();
        return;
    }
    try {
        var resp = await fetch('/api/licenca/verificar', {
            method: 'POST', headers: CABECALHOS_JSON, body: JSON.stringify({})
        });
        if (!resp.ok) return;
        var situacao = await resp.json();

        if (situacao.estado === 'paga') {
            exibirToast('Licenca ativada. Bom trabalho!');
            registrarLicencaLiberada();
            return;
        }
        // Cobranca cancelada, recusada ou estornada: perguntar de novo nao muda
        // a resposta. Parar aqui e o que evita a tela girar para sempre.
        if (situacao.encerrado) {
            pararVerificacaoDaLicenca();
            _avisarNaCaixaDaLicenca('Esta cobranca foi encerrada sem pagamento. Gere uma nova para tentar de novo.');
            return;
        }
        // Ha cobranca em aberto de uma execucao anterior: retoma a espera sem
        // pedir ao operador que gere outra.
        if (primeira && situacao.pagamento_id) iniciarVerificacaoDaLicenca();
    } catch (_) {
        // Sem rede: a proxima rodada tenta.
    }
}
