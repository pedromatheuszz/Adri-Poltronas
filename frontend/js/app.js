const API_URL = '/api/clientes';
let modoSelecaoAtivo = false;
let saindoSelecao = false;
let intervaloChecagem = null;
let debounceTimer;
var filtrosAtivos = { tipos: ['Entrega', 'Retirada'], cidades: [] };

// ---------------------------------------------------------------------------
// CSRF Token - integridade de requisicoes
// ---------------------------------------------------------------------------
function _obterCsrfToken() {
    var match = document.cookie.match(/csrf_token=([^;]+)/);
    if (match) return match[1];
    var meta = document.querySelector('meta[name="csrf-token"]');
    if (meta) return meta.getAttribute('content');
    return null;
}

async function fetchSeguro(url, options) {
    options = options || {};
    options.headers = options.headers || {};
    var token = _obterCsrfToken();
    if (token && !options.headers['X-CSRF-Token']) {
        options.headers['X-CSRF-Token'] = token;
    }
    if (!options.headers['Content-Type'] && !(options.body instanceof FormData)) {
        options.headers['Content-Type'] = 'application/json';
    }
    try {
        var resp = await fetch(url, options);
        var csrfHeader = resp.headers.get('X-CSRF-Token');
        if (csrfHeader) {
            document.cookie = 'csrf_token=' + csrfHeader + '; path=/; SameSite=Lax';
        }
        return resp;
    } catch (e) {
        console.error('[fetchSeguro] Erro:', e);
        throw e;
    }
}

// -----------------------------------------------------------------------------
// Sessao ausente
//
// Ate a 1.3.0 a leitura da API respondia sem sessao, entao "app aberto sem
// conta conectada" nunca precisou ser um estado: a tela carregava como
// qualquer outra. Fechada essa folga, o MESMO app passou a mostrar a casca com
// os zeros escritos no proprio HTML -- "0 Total Clientes", "R$ 0,00 em atraso"
// -- enquanto o console acumulava 401 que ninguem ve.
//
// O sintoma nao era um erro na tela. Era pior: numero errado com ar de numero
// certo. Quem abrisse o app sem ter conectado leria "nada a receber" e
// acreditaria.
//
// Sao dois mecanismos. O portao em `iniciarAplicacao()` resolve a abertura --
// nao se pede dado antes de saber se ha sessao. Este gancho resolve o resto:
// a sessao que expira com o app aberto, e qualquer chamada futura que alguem
// escreva sem lembrar do assunto.
// -----------------------------------------------------------------------------
var _semSessao = false;

// `/api/auth/` e `/api/health` respondem antes de existir sessao por desenho;
// um 401 vindo delas significaria outra coisa, e nao "precisa conectar".
function _ehRotaQueExigeSessao(url) {
    if (typeof url !== 'string' || url.indexOf('/api/') !== 0) return false;
    return url.indexOf('/api/auth/') !== 0 && url.indexOf('/api/health') !== 0;
}

function registrarSessaoAusente() {
    if (_semSessao) return;
    _semSessao = true;
    // O que estiver na tela deixou de valer; a proxima abertura precisa
    // buscar de novo em vez de confiar no que ficou.
    _dadosJaCarregados = false;
    mostrarPainelSemConexao();
}

function registrarSessaoPresente() {
    if (!_semSessao) return;
    _semSessao = false;
    esconderPainelSemConexao();
}

// O cabecalho da topbar fica por conta da troca de abas, e nao deste painel.
//
// A primeira versao daqui o trocava por "Conecte-se para comecar", o que
// parecia melhor e nao era: trocar de aba com o painel aberto reescreve o
// titulo, e o valor guardado para restaurar depois envelhecia na hora. Quem
// conectasse estando em "Pagamentos" veria a tela voltar dizendo "Dashboard".
//
// Alem disso as duas informacoes sao diferentes e ambas verdadeiras: o titulo
// diz onde o operador esta, o painel diz por que nao ha numero ali.
function mostrarPainelSemConexao() {
    var painel = document.getElementById('painelSemConexao');
    var casca = document.getElementById('appShell');
    if (painel) painel.hidden = false;
    if (casca) casca.classList.add('sem-conexao');
}

function esconderPainelSemConexao() {
    var painel = document.getElementById('painelSemConexao');
    var casca = document.getElementById('appShell');
    if (painel) painel.hidden = true;
    if (casca) casca.classList.remove('sem-conexao');
}

// Patch do fetch original para injetar CSRF automaticamente
var _fetchOriginal = window.fetch;
window.fetch = function(url, options) {
    if (typeof url === 'string' && (url.startsWith('/api/') || url.startsWith('/api/auth/logout') || url.startsWith('/api/auth/login'))) {
        options = options || {};
        options.headers = options.headers || {};
        if (!options.headers['X-CSRF-Token']) {
            var tok = _obterCsrfToken();
            if (tok) options.headers['X-CSRF-Token'] = tok;
        }
        if (!options.headers['Content-Type'] && !(options.body instanceof FormData)) {
            options.headers['Content-Type'] = 'application/json';
        }
    }
    var promessa = _fetchOriginal.apply(this, arguments);
    if (_ehRotaQueExigeSessao(url)) {
        // Observa sem consumir: a promessa devolvida a quem chamou e a
        // original, entao o corpo continua intacto para ele ler.
        promessa.then(function(resposta) {
            if (!resposta) return;
            if (resposta.status === 401) registrarSessaoAusente();
            // 402 Payment Required: a licenca venceu. Mesmo desenho do 401 --
            // um gancho central em vez de tratamento em cada chamada, para que
            // o app nao dependa de alguem lembrar do assunto ao escrever a
            // proxima rota.
            if (resposta.status === 402) registrarLicencaVencida();
        }, function() { /* rede fora: e outro assunto, tratado em tentarBackend */ });
    }
    return promessa;
};


// -----------------------------------------------------------------------------
// Licenca de uso
//
// Trinta dias de teste a partir da primeira abertura; depois, licenca paga.
// O bloqueio de verdade e do backend (`_exigir_licenca`, que responde 402); o
// que existe aqui e a tela que explica e o caminho para resolver.
//
// O pagamento e verificado PERGUNTANDO ao Mercado Pago, e nao esperando
// webhook: o backend escuta em loopback e um servidor da internet nao alcanca
// este endereco. Mesma inversao ja usada para o Asaas em reconciliacao.py.
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
    var casca = document.getElementById('appShell');
    if (painel) painel.hidden = false;
    if (casca) casca.classList.add('licenca-vencida');

    var valor = document.getElementById('licencaValor');
    if (valor && situacao && situacao.valor_centavos) {
        valor.textContent = _formatarReais(situacao.valor_centavos);
    }
}

function esconderPainelLicenca() {
    var painel = document.getElementById('painelLicenca');
    var casca = document.getElementById('appShell');
    if (painel) painel.hidden = true;
    if (casca) casca.classList.remove('licenca-vencida');
}

function registrarLicencaVencida(situacao) {
    if (_licencaVencida) return;
    _licencaVencida = true;
    _dadosJaCarregados = false;
    mostrarPainelLicenca(situacao);
    // Ha cobranca aberta de uma execucao anterior? Entao ja se comeca
    // perguntando, sem pedir ao operador que refaca algo que ele ja fez.
    verificarPagamentoDaLicenca(true);
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

    // Mesmo cuidado da cobranca do Asaas: o base64 do QR passa por
    // `base64Seguro` antes de virar `src`, e o payload por `escaparHtml`.
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

// Atualiza o cookie CSRF a partir do header da resposta inicial
(function() {
    fetch('/').then(function(r) { var t = r.headers.get('X-CSRF-Token'); if(t) document.cookie = 'csrf_token=' + t + '; path=/; SameSite=Lax'; }).catch(function(){});
})();

function escaparHtml(str) {
    if (!str) return '';
    return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}

// Base64 valido nao contem aspas nem `<`. Um valor fora do alfabeto nao e
// escapado, e sim recusado: um "QR Code" que nao e base64 nao tem uso, e
// concatena-lo dentro de src="data:image/png;base64,..." era o unico ponto do
// arquivo em que um atributo era montado sem passar por escaparHtml.
function base64Seguro(valor) {
    var texto = String(valor || '');
    return /^[A-Za-z0-9+/\r\n]*={0,2}$/.test(texto) ? texto.replace(/\s/g, '') : '';
}

// href montado por concatenacao aceita apenas http(s). escaparHtml sozinho
// impede quebrar o atributo, mas nao impede um `javascript:` inteiro.
function urlSegura(valor) {
    var texto = String(valor || '').trim();
    return /^https?:\/\//i.test(texto) ? texto : '';
}

// -----------------------------------------------------------------------------
// Disponibilidade do backend
//
// O servidor roda em 127.0.0.1: `navigator.onLine` mede a conexao com a
// internet, nao com ele. Desligar o WiFi jogava todo o CRUD na fila offline --
// gravando clientes com id negativo no IndexedDB -- enquanto o backend local
// respondia normalmente. O unico sinal confiavel e a propria requisicao falhar
// por rede: `fetch` rejeita nesse caso, enquanto um 4xx/5xx e uma RESPOSTA do
// servidor, e nao indisponibilidade.
// -----------------------------------------------------------------------------
var CABECALHOS_JSON = { 'Content-Type': 'application/json' };

async function tentarBackend(url, opcoes) {
    try {
        var resposta = await fetch(url, opcoes);
        // Sem service worker, a queda de rede vira excecao e cai no catch.
        // COM service worker registrado, ele intercepta a falha e devolve uma
        // resposta sintetica -- o `fetch` resolve, e o catch nunca dispara.
        // O header e o que revela esse caso; sem esta checagem, o app tratava
        // o envelope de offline como se fosse dado do servidor.
        if (resposta.headers.get('X-Adri-Offline')) {
            console.warn('[backend] offline (service worker):', url);
            return { semBackend: true };
        }
        return { resposta: resposta };
    } catch (erro) {
        console.warn('[backend] indisponivel:', url, erro);
        return { semBackend: true };
    }
}

function exibirToast(mensagem, tipo) {
    tipo = tipo || 'success';
    // Com o painel de "sem conexao" na tela, todo erro de carregamento tem a
    // mesma causa e ja esta explicada la. Deixar passar produzia o pior dos
    // dois mundos: a explicacao calma no meio da tela e, por cima dela, um
    // "Erro ao carregar pagamentos." vermelho que nao diz o que fazer.
    //
    // A ordem funciona porque o gancho do 401 e registrado no momento do
    // fetch: ele roda antes de quem chamou retomar do `await`, entao
    // `_semSessao` ja esta ligado quando o catch tenta avisar.
    if (_semSessao && tipo === 'error') {
        console.warn('[sessao] erro suprimido (o painel ja explica):', mensagem);
        return;
    }
    var toast = document.getElementById('toast');
    if (!toast) return;
    toast.innerText = mensagem;
    // A cor sai do CSS por classe, e nao de um hex escrito aqui: assim o aviso
    // acompanha o tema claro/escuro em vez de ficar preso a um verde fixo.
    toast.className = (tipo === 'success' ? 'toast-sucesso' : 'toast-erro') + ' show';
    clearTimeout(_temporizadorToast);
    _temporizadorToast = setTimeout(function() {
        toast.classList.remove('show');
    }, 3000);
}
// Guardado fora da funcao: dois toasts em sequencia rapida faziam o timer do
// primeiro apagar o segundo no meio da exibicao.
var _temporizadorToast = null;

// -----------------------------------------------------------------------------
// Confirmacao
//
// Substitui o confirm() nativo, que ignora o tema do app e ainda exibe o
// endereco do servidor ("127.0.0.1:5000 diz"). Devolve uma Promise<boolean>,
// entao o uso fica igual ao do nativo: `if (!await confirmarAcao({...})) return;`
// -----------------------------------------------------------------------------
var ICONES_CONFIRMACAO = {
    excluir: '<svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>',
    alerta: '<svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>',
    desconectar: '<svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18.36 6.64a9 9 0 1 1-12.73 0"/><line x1="12" y1="2" x2="12" y2="12"/></svg>'
};

// -----------------------------------------------------------------------------
// Modais
//
// As janelas modais sao elementos <dialog>. Abrir por showModal() entrega de
// graca o que antes era imitado a mao: foco preso dentro da janela, fechamento
// com Esc e fundo escurecido pelo ::backdrop. A classe `ativo` continua sendo
// aplicada como reserva para o caso raro de um motor sem suporte a <dialog>.
// -----------------------------------------------------------------------------
function abrirModal(alvo) {
    var el = typeof alvo === 'string' ? document.getElementById(alvo) : alvo;
    if (!el) return null;
    if (typeof el.showModal === 'function') {
        if (!el.open) el.showModal();
    } else {
        el.classList.add('ativo');
    }
    return el;
}

function fecharModal(alvo) {
    var el = typeof alvo === 'string' ? document.getElementById(alvo) : alvo;
    if (!el) return null;
    if (typeof el.close === 'function' && el.open) el.close();
    el.classList.remove('ativo');
    return el;
}

function modalAberto() {
    return document.querySelector('dialog[open]') ||
           document.querySelector('.modal-overlay.ativo');
}

function confirmarAcao(opcoes) {
    opcoes = opcoes || {};
    var overlay = document.getElementById('modalConfirmar');

    // Sem o modal no DOM, cai para o nativo em vez de travar o fluxo.
    if (!overlay) return Promise.resolve(window.confirm(opcoes.mensagem || 'Confirmar?'));

    var caixa = overlay.querySelector('.modal-box');
    var elIcone = document.getElementById('modalConfirmarIcone');
    var elTitulo = document.getElementById('modalConfirmarTitulo');
    var elMsg = document.getElementById('modalConfirmarMsg');
    var btnOk = document.getElementById('modalConfirmarOk');
    var btnCancelar = document.getElementById('modalConfirmarCancelar');
    var campo = document.getElementById('modalConfirmarCampo');
    var rotulo = document.getElementById('modalConfirmarRotulo');
    var entrada = document.getElementById('modalConfirmarTexto');

    caixa.setAttribute('data-variante', opcoes.variante || 'perigo');
    elIcone.innerHTML = ICONES_CONFIRMACAO[opcoes.icone] || ICONES_CONFIRMACAO.alerta;
    elTitulo.textContent = opcoes.titulo || 'Confirmar';
    elMsg.textContent = opcoes.mensagem || '';
    btnOk.textContent = opcoes.textoConfirmar || 'Confirmar';
    btnCancelar.textContent = opcoes.textoCancelar || 'Cancelar';

    // `campoTexto` transforma a confirmacao numa pergunta: usado onde a
    // decisao do operador contraria o que o sistema apuraria sozinho e o
    // motivo precisa acompanhar o registro. Com ele a Promise resolve com o
    // texto (ou null ao cancelar) em vez de um booleano -- e como texto vazio
    // e falsy, quem so testa `if (!resposta)` continua funcionando.
    var pedeTexto = !!(opcoes.campoTexto && campo && entrada);
    if (campo) campo.hidden = !pedeTexto;
    if (pedeTexto) {
        rotulo.textContent = opcoes.campoTexto.rotulo || 'Motivo';
        entrada.placeholder = opcoes.campoTexto.exemplo || '';
        entrada.value = '';
        btnOk.disabled = true;
    } else if (btnOk.disabled) {
        btnOk.disabled = false;
    }

    return new Promise(function(resolver) {
        var finalizado = false;

        function encerrar(resultado) {
            if (finalizado) return;
            finalizado = true;
            fecharModal(overlay);
            btnOk.removeEventListener('click', aoConfirmar);
            btnCancelar.removeEventListener('click', aoCancelar);
            overlay.removeEventListener('click', aoClicarFora);
            document.removeEventListener('keydown', aoTeclar);
            if (pedeTexto) {
                entrada.removeEventListener('input', aoDigitar);
                btnOk.disabled = false;
            }
            resolver(resultado);
        }

        function valorConfirmado() {
            if (!pedeTexto) return true;
            return entrada.value.trim();
        }
        function valorCancelado() { return pedeTexto ? null : false; }

        function aoDigitar() { btnOk.disabled = !entrada.value.trim(); }
        function aoConfirmar() {
            if (pedeTexto && !entrada.value.trim()) return;
            encerrar(valorConfirmado());
        }
        function aoCancelar() { encerrar(valorCancelado()); }
        function aoClicarFora(e) { if (e.target === overlay) encerrar(valorCancelado()); }
        function aoTeclar(e) {
            if (e.key === 'Escape') encerrar(valorCancelado());
            else if (e.key === 'Enter' && document.activeElement !== btnCancelar) {
                e.preventDefault(); aoConfirmar();
            }
        }

        btnOk.addEventListener('click', aoConfirmar);
        btnCancelar.addEventListener('click', aoCancelar);
        overlay.addEventListener('click', aoClicarFora);
        document.addEventListener('keydown', aoTeclar);
        if (pedeTexto) entrada.addEventListener('input', aoDigitar);

        abrirModal(overlay);
        // Com campo, o foco vai para ele: o operador chegou ali para escrever.
        // Sem campo, foco no cancelar -- acao destrutiva nao deve ser
        // confirmada por engano por quem chegou pelo teclado.
        setTimeout(function(){ (pedeTexto ? entrada : btnCancelar).focus(); }, 60);
    });
}

function aplicarMascaraCep(e) {
    var value = e.target.value.replace(/\D/g, '');
    if (value.length > 5) value = value.replace(/^(\d{5})(\d)/, '$1-$2');
    e.target.value = value;
}

// Titulo e subtitulo de cada modulo, exibidos no cabecalho. Ficam aqui, e nao
// no HTML de cada aba, porque o cabecalho e um so e precisa ser reescrito a
// cada troca -- e porque assim a lista de modulos existe num lugar unico.
var PAGINAS = {
    dashboard:  { titulo: 'Dashboard',  descricao: 'Visao geral do cadastro e das financas' },
    pedidos:    { titulo: 'Pedidos',    descricao: 'O que foi encomendado, por quanto e para quando' },
    clientes:   { titulo: 'Clientes',   descricao: 'Cadastro, edicao e exportacao da base de clientes' },
    produtos:   { titulo: 'Produtos',   descricao: 'Catalogo de modelos usado nos pedidos' },
    entregas:   { titulo: 'Entregas',   descricao: 'Agenda de entregas e retiradas' },
    mapa:       { titulo: 'Mapa',       descricao: 'Distribuicao geografica das entregas e retiradas' },
    pagamentos: { titulo: 'Pagamentos', descricao: 'Recebimentos, cobrancas e situacao financeira' },
    relatorios: { titulo: 'Relatorios', descricao: 'Consultas filtradas e exportacao de dados' }
};

function atualizarCabecalho(aba) {
    var pagina = PAGINAS[aba];
    if (!pagina) return;
    var titulo = document.getElementById('tituloPagina');
    var descricao = document.getElementById('descricaoPagina');
    if (titulo) titulo.textContent = pagina.titulo;
    if (descricao) descricao.textContent = pagina.descricao;
    // O titulo da janela do Electron acompanha: com varias janelas abertas na
    // barra de tarefas, "Adri Poltronas" repetido nao distingue nada.
    document.title = pagina.titulo + ' — Adri Poltronas';
}

function trocarAba(aba) {
    atualizarCabecalho(aba);
    // Mantem estado visual, semantica ARIA e o atributo HTML5 `hidden` juntos.
    document.querySelectorAll('.tab-content').forEach(function(s) {
        s.classList.remove('active');
        s.hidden = true;
        s.style.display = '';
    });
    document.querySelectorAll('.nav-tab').forEach(function(t){
        t.classList.remove('active');
        t.setAttribute('aria-selected', 'false');
        t.setAttribute('tabindex', '-1');
    });
    var section = document.getElementById('aba-' + aba);
    var tab = document.getElementById('tab-' + aba);
    if (section) {
        // Force display:block first (opacity still 0 from CSS), then trigger opacity transition
        section.hidden = false;
        section.style.display = 'block';
        section.offsetHeight; // force reflow so transition fires
        section.classList.add('active');
    }
    if (tab) {
        tab.classList.add('active');
        tab.setAttribute('aria-selected', 'true');
        tab.removeAttribute('tabindex');
    }
    if (aba === 'dashboard') { carregarDashboardGraficos(); }
    if (aba === 'pedidos') { carregarPedidos(); carregarProdutos(); }
    if (aba === 'produtos') { carregarProdutos(); }
    if (aba === 'entregas') { carregarEntregas(); }
    if (aba === 'mapa') { setTimeout(function() { initMapa(); carregarMapaClientes(); }, 100); }
    if (aba === 'clientes') { atualizarAvisoDePendenciasComErro(); }
    // `pagamentos` e `relatorios` nao carregam nada: as duas areas estao
    // desativadas nesta versao e a secao ja traz o aviso escrito no HTML.
    // Pedir dado a elas so renderia 503 no console.
}

var chartInstances = {};

var _dadosJaCarregados = false;

// A licenca ja foi consultada nesta execucao? Enquanto for `false`, nao se
// pede dado nenhum: "ainda nao sei" e diferente de "esta tudo certo", e tratar
// os dois igual foi exatamente o defeito abaixo.
var _licencaVerificada = false;

// Os DOIS portoes precisam estar abertos para o app mostrar dado: sessao
// Microsoft e licenca vigente.
//
// Antes, `checarLoginExistente` chamava `carregarDadosDoApp` direto, e ele roda
// antes de a licenca ser consultada. Numa instalacao com o teste vencido isso
// disparava quatro requisicoes que voltavam 402 -- deixando na tela os zeros
// escritos no HTML -- e, pior, marcava `_dadosJaCarregados`. Quando o operador
// pagava e a tela liberava, o carregamento nao acontecia mais: o app ficava
// aberto, funcional e mostrando "0 Total Clientes" sobre um banco cheio.
function liberarDadosSeOsPortoesAbrirem() {
    if (!_licencaVerificada) return;
    if (_semSessao || _licencaVencida) return;
    carregarDadosDoApp();
}

// Tudo o que fala com /api/ e precisa de sessao e licenca.
function carregarDadosDoApp() {
    if (_dadosJaCarregados) return;
    _dadosJaCarregados = true;
    carregarClientes();
    carregarNotificacoes();
    carregarDashboardGraficos();
}

// O portao. Perguntar PRIMEIRO se ha sessao, e so entao decidir, e o que
// impede a tela de aparecer preenchida com os zeros do HTML enquanto quatro
// requisicoes voltam 401 em silencio.
async function iniciarAplicacao() {
    var logado = false;
    try {
        logado = await checarLoginExistente();
    } catch (_) {
        // /api/auth/status e isenta de sessao; falhar aqui significa backend
        // fora do ar, nao falta de conta. Tratar como desconectado e o lado
        // seguro: melhor pedir conexao do que mostrar numero que nao veio.
    }
    if (!logado) {
        registrarSessaoAusente();
        return;
    }

    // A licenca so e consultada DEPOIS de haver sessao, na mesma ordem dos
    // guardas do backend: quem nao esta autenticado no app nao precisa saber
    // em que pe esta a licenca dele.
    await checarLicenca();
    liberarDadosSeOsPortoesAbrirem();
}

document.addEventListener('DOMContentLoaded', function() {
    initTheme();
    initSidebar();
    registrarAtalhosTeclado();

    initObservacoesCounter();
    marcarVersaoBeta();
    iniciarAplicacao();

    // O modulo comercial vive em comercial.js; a checagem cobre o caso de o
    // arquivo nao ter carregado, para o resto da tela seguir funcionando.
    if (typeof registrarEventosComerciais === 'function') registrarEventosComerciais();

    var selectAll = document.getElementById('selectAll');
    if (selectAll) {
        selectAll.addEventListener('change', function() {
            document.querySelectorAll('.client-checkbox').forEach(function(cb){ cb.checked = selectAll.checked; });
        });
    }

    document.addEventListener('change', function(e) {
        if (e.target && e.target.classList && e.target.classList.contains('client-checkbox')) {
            var checkboxes = document.querySelectorAll('.client-checkbox');
            var total = checkboxes.length;
            var marcados = Array.from(checkboxes).filter(function(cb){ return cb.checked; }).length;
            if (selectAll) {
                selectAll.checked = total > 0 && marcados === total;
                selectAll.indeterminate = marcados > 0 && marcados < total;
            }
        }
    });

    var form = document.getElementById('clienteForm');
    if (form) {
        form.addEventListener('submit', async function(e) {
            e.preventDefault();
            var id = document.getElementById('clienteId').value;
            var dados = {
                nome: document.getElementById('nome').value,
                cep: document.getElementById('cep').value,
                rua: document.getElementById('rua').value,
                bairro: document.getElementById('bairro').value,
                cidade: document.getElementById('cidade').value,
                entrega_retirada: document.getElementById('entregaRetirada').value,
                observacoes: document.getElementById('observacoes').value
            };
            if (id) { await atualizarClienteServidor(parseInt(id, 10), dados); }
            else { await registrarNovoCliente(dados); }
        });
    }

    var inputPesquisa = document.getElementById('inputPesquisa');
    if (inputPesquisa) {
        inputPesquisa.addEventListener('input', function() {
            clearTimeout(debounceTimer);
            debounceTimer = setTimeout(function(){ carregarClientes(); }, 300);
        });
    }

    var inputCep = document.getElementById('cep');
    if (inputCep) inputCep.addEventListener('input', aplicarMascaraCep);

    var btnCancelar = document.getElementById('btnCancelar');
    if (btnCancelar) btnCancelar.addEventListener('click', cancelarEdicao);

    document.querySelectorAll('.modal-overlay').forEach(function(overlay) {
        overlay.addEventListener('click', function(e) {
            if (e.target === overlay) fecharModal(overlay);
        });
    });

    document.addEventListener('click', function(e) {
        var dropdown = document.getElementById('filtroDropdown');
        var btnFiltro = document.getElementById('btnFiltro');
        if (!dropdown) return;
        if (!btnFiltro.contains(e.target) && !dropdown.contains(e.target)) {
            dropdown.classList.remove('ativo');
            btnFiltro.classList.remove('ativo');
            btnFiltro.setAttribute('aria-expanded', 'false');
        }
    });

    // O modal de confirmacao e cabeado dentro de confirmarAcao(), que registra e
    // remove os listeners a cada uso — nao precisa de wiring fixo aqui.

    // Acoes das notificacoes por delegacao: a lista e reconstruida a cada
    // atualizacao, entao listeners por item seriam perdidos.
    var listaNotifs = document.getElementById('notificacoesLista');
    if (listaNotifs) {
        listaNotifs.addEventListener('click', function(e) {
            var botao = e.target.closest('.notif-acao');
            if (!botao) return;
            e.stopPropagation();
            var acao = botao.getAttribute('data-acao');
            if (acao === 'lida') marcarNotificacaoLida(botao.getAttribute('data-chave'), true);
            else if (acao === 'naolida') marcarNotificacaoLida(botao.getAttribute('data-chave'), false);
            else if (acao === 'entrega') marcarEntregaConcluida(parseInt(botao.getAttribute('data-id'), 10));
        });
    }

    var btnTodasLidas = document.getElementById('btnMarcarTodasLidas');
    if (btnTodasLidas) btnTodasLidas.addEventListener('click', marcarTodasNotificacoesLidas);

    var btnMais = document.getElementById('btnCarregarMaisClientes');
    if (btnMais) btnMais.addEventListener('click', carregarMaisClientes);

    var btnRestaurar = document.getElementById('btnRestaurarBanco');
    if (btnRestaurar) btnRestaurar.addEventListener('click', abrirModalRestaurar);

    var fecharRestaurar = document.getElementById('modalRestaurarFechar');
    if (fecharRestaurar) fecharRestaurar.addEventListener('click', function(){ fecharModal('modalRestaurar'); });

    var listaCopias = document.getElementById('listaCopias');
    if (listaCopias) {
        listaCopias.addEventListener('click', function(e) {
            var botao = e.target.closest('button[data-restaurar]');
            if (botao) restaurarCopia(botao.getAttribute('data-restaurar'));
        });
    }

    var btnVerPendencias = document.getElementById('btnVerPendenciasComErro');
    if (btnVerPendencias) btnVerPendencias.addEventListener('click', abrirPendenciasComErro);

    var fecharPendencias = document.getElementById('modalPendenciasFechar');
    if (fecharPendencias) fecharPendencias.addEventListener('click', function(){ fecharModal('modalPendenciasComErro'); });

    var listaPendencias = document.getElementById('listaPendenciasComErro');
    if (listaPendencias) {
        // Delegacao: os botoes nascem a cada abertura do modal, e prende-los
        // um a um vazaria listener a cada renderizacao.
        listaPendencias.addEventListener('click', function(e) {
            var botao = e.target.closest('button[data-reenviar], button[data-descartar]');
            if (botao) _acaoNaPendenciaComErro(botao);
        });
    }

    atualizarAvisoDePendenciasComErro();

    var modalNomeCancelar = document.getElementById('modalNomeCancelar');
    var modalNomeConfirmar = document.getElementById('modalNomeConfirmar');
    if (modalNomeCancelar) modalNomeCancelar.addEventListener('click', function(){ fecharModal('modalNomeArquivo'); });
    if (modalNomeConfirmar) modalNomeConfirmar.addEventListener('click', function() {
        fecharModal('modalNomeArquivo');
        if (window._confirmNomeCallback) window._confirmNomeCallback();
    });

    var modalImportarCancelar = document.getElementById('modalImportarCancelar');
    if (modalImportarCancelar) modalImportarCancelar.addEventListener('click', function(){ fecharModal('modalImportar'); });

    var tabelaClientes = document.getElementById('tabelaClientes');
    if (tabelaClientes) {
        tabelaClientes.addEventListener('click', function(e) {
            var btn = e.target.closest('[data-action]');
            if (!btn) return;
            var action = btn.getAttribute('data-action');
            var id = parseInt(btn.getAttribute('data-id'));
            if (action === 'editar') {
                editarCliente(id,
                    btn.getAttribute('data-nome') || '',
                    btn.getAttribute('data-cep') || '',
                    btn.getAttribute('data-rua') || '',
                    btn.getAttribute('data-bairro') || '',
                    btn.getAttribute('data-cidade') || '',
                    btn.getAttribute('data-tipo') || 'Entrega',
                    btn.getAttribute('data-obs') || ''
                );
            } else if (action === 'excluir') {
                excluirClienteServidor(id);
            }
        });
    }

    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') {
            var modalAtivo = modalAberto();
            if (!modalAtivo) {
                var inputId = document.getElementById('clienteId');
                if (inputId && inputId.value) { cancelarEdicao(); exibirToast('Edicao cancelada.'); }
            } else { fecharModal(modalAtivo); }
        }
    });
});

async function carregarDashboardGraficos() {
    try {
        var resp = await fetch('/api/dashboard/dados?t=' + Date.now());
        if (!resp.ok) return;
        var dados = await resp.json();
        if (dados.erro) return;

        var paleta = paletaGraficos();

        // Calcular métricas a partir dos dados do gráfico
        var tipoLabels = Object.keys(dados.por_tipo || {});
        var tipoValores = Object.values(dados.por_tipo || {});
        var totalClientes = tipoValores.reduce(function(a, b) { return a + b; }, 0);
        var totalEntregas = dados.por_tipo['Entrega'] || 0;
        var totalRetiradas = dados.por_tipo['Retirada'] || 0;
        var cadastros30d = (dados.timeline.valores || []).reduce(function(a, b) { return a + b; }, 0);
        var elTC = document.getElementById('metricTotalClientes');
        var elEN = document.getElementById('metricEntregas');
        var elRE = document.getElementById('metricRetiradas');
        var el30 = document.getElementById('metricCadastros30d');
        if (elTC) elTC.textContent = totalClientes;
        if (elEN) elEN.textContent = totalEntregas;
        if (elRE) elRE.textContent = totalRetiradas;
        if (el30) el30.textContent = cadastros30d;


        // Gráfico Pizza: Entregas vs Retiradas
        var tipoLabels = Object.keys(dados.por_tipo || {});
        var tipoValores = Object.values(dados.por_tipo || {});
        if (tipoLabels.length > 0) {
            var ctxTipo = document.getElementById('chartEntregaRetirada');
            if (ctxTipo) {
                if (chartInstances.tipo) chartInstances.tipo.destroy();
                chartInstances.tipo = new Chart(ctxTipo, {
                    type: 'doughnut',
                    data: {
                        labels: tipoLabels,
                        datasets: [{
                            data: tipoValores,
                            backgroundColor: tipoLabels.map(function(l) { return l === 'Retirada' ? paleta.alerta : paleta.sucesso; }),
                            // A borda na cor da superficie separa as fatias sem
                            // desenhar um contorno que compete com os dados.
                            borderColor: paleta.superficie,
                            borderWidth: 2
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: {
                            legend: { position: 'bottom', labels: { color: paleta.texto, padding: 16, font: { size: 12 } } }
                        }
                    }
                });
            }
        }

        // Gráfico Barras: Top Cidades
        var cidLabels = dados.cidades.labels || [];
        var cidValores = dados.cidades.valores || [];
        if (cidLabels.length > 0) {
            var ctxCid = document.getElementById('chartCidades');
            if (ctxCid) {
                if (chartInstances.cidades) chartInstances.cidades.destroy();
                chartInstances.cidades = new Chart(ctxCid, {
                    type: 'bar',
                    data: {
                        labels: cidLabels,
                        datasets: [{
                            label: 'Clientes',
                            data: cidValores,
                            backgroundColor: paleta.primaria,
                            borderWidth: 0,
                            borderRadius: 4,
                            maxBarThickness: 34
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: { legend: { display: false } },
                        scales: {
                            x: { ticks: { color: paleta.texto, font: { size: 11 } }, grid: { display: false } },
                            y: { ticks: { color: paleta.texto, stepSize: 1 }, grid: { color: paleta.grade } }
                        }
                    }
                });
            }
        }

        // Gráfico Linha: Timeline
        var tlLabels = dados.timeline.labels || [];
        var tlValores = dados.timeline.valores || [];
        if (tlLabels.length > 0) {
            var ctxTL = document.getElementById('chartTimeline');
            if (ctxTL) {
                if (chartInstances.timeline) chartInstances.timeline.destroy();
                chartInstances.timeline = new Chart(ctxTL, {
                    type: 'line',
                    data: {
                        labels: tlLabels,
                        datasets: [{
                            label: 'Cadastros',
                            data: tlValores,
                            borderColor: paleta.info,
                            backgroundColor: 'transparent',
                            fill: false,
                            tension: 0.3,
                            pointRadius: 2,
                            pointBackgroundColor: paleta.info
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: { legend: { display: false } },
                        scales: {
                            x: { ticks: { color: paleta.texto, maxTicksLimit: 10, font: { size: 11 } }, grid: { display: false } },
                            y: { ticks: { color: paleta.texto, stepSize: 1 }, grid: { color: paleta.grade }, beginAtZero: true }
                        }
                    }
                });
            }
        }

        // Últimos clientes
        var ulEl = document.getElementById('ultimosClientes');
        if (ulEl && dados.ultimos_clientes && dados.ultimos_clientes.length > 0) {
            ulEl.innerHTML = dados.ultimos_clientes.map(function(c) {
                var badgeClass = c.tipo === 'Retirada' ? 'badge-retirada' : 'badge-entrega';
                var nome = escaparHtml(c.nome);
                return '<div class="ultimo-cliente-item">' +
                    '<span class="ultimo-cliente-nome" title="' + nome + '">' + nome + '</span>' +
                    '<span class="ultimo-cliente-meta">' + escaparHtml(c.cidade || '-') +
                    '<span class="' + badgeClass + '">' + escaparHtml(c.tipo) + '</span></span>' +
                    '</div>';
            }).join('');
        }
    } catch(e) { console.error('Erro ao carregar gráficos:', e); exibirToast('Erro ao carregar dashboard.', 'error'); }
}

// -----------------------------------------------------------------------------
// Dashboard financeiro
// -----------------------------------------------------------------------------
function formatarReal(valor) {
    return 'R$ ' + (Number(valor) || 0).toFixed(2).replace('.', ',').replace(/\B(?=(\d{3})+(?!\d))/g, '.');
}

function rotuloMes(chave) {
    // 'AAAA-MM' -> 'ago/26'
    var nomes = ['jan','fev','mar','abr','mai','jun','jul','ago','set','out','nov','dez'];
    var partes = String(chave).split('-');
    if (partes.length !== 2) return chave;
    return nomes[parseInt(partes[1], 10) - 1] + '/' + partes[0].slice(2);
}

// -----------------------------------------------------------------------------
// Paleta dos graficos
//
// As cores sao lidas dos tokens CSS em vez de escritas aqui. Duas razoes: os
// graficos acompanham a troca de tema sem codigo extra, e a identidade visual
// continua morando num arquivo so (tokens.css). Antes havia sete hex soltos
// no meio das configuracoes do Chart.js -- azul e roxo que nao existiam em
// nenhum outro lugar da interface.
// -----------------------------------------------------------------------------
function token(nome, reserva) {
    var valor = getComputedStyle(document.documentElement).getPropertyValue(nome).trim();
    return valor || reserva;
}

function corDoTexto() {
    return token('--cor-texto-2', '#6B6153');
}

function corDaGrade() {
    return token('--cor-borda', '#E0D8C9');
}

function paletaGraficos() {
    return {
        primaria: token('--cor-primaria', '#8A5A3B'),
        sucesso:  token('--cor-sucesso', '#4E6B3C'),
        alerta:   token('--cor-alerta', '#A8761C'),
        info:     token('--cor-info', '#4A6480'),
        texto:    corDoTexto(),
        grade:    corDaGrade(),
        superficie: token('--cor-superficie', '#FBF9F5')
    };
}



var CHAVE_SIDEBAR = 'adri-sidebar';

function initSidebar() {
    // A preferencia acompanha o operador entre sessoes: quem trabalha em tela
    // pequena deixa recolhido e nao quer refazer isso a cada abertura.
    var salvo = null;
    try { salvo = localStorage.getItem(CHAVE_SIDEBAR); } catch(_) {}
    // `salvo !== null` distingue "escolheu deixar aberta" de "nunca escolheu".
    // Sem essa distincao, initSidebar marcava TODA sessao como escolha manual
    // e a regra de recolhimento automatico em tela estreita nunca chegava a
    // valer -- a barra comia 248px de uma janela de 1024px.
    aplicarEstadoSidebar(salvo === 'recolhida', salvo !== null);
    registrarNavegacaoPorSetas();
}

function aplicarEstadoSidebar(recolhida, escolhaManual) {
    var barra = document.getElementById('sidebar');
    var botao = document.getElementById('btnSidebarToggle');
    if (!barra) return;
    barra.classList.toggle('recolhida', recolhida);
    // `expandida-manual` vence a regra de largura que recolhe sozinha: uma
    // escolha explicita do usuario nao pode ser desfeita pelo CSS.
    barra.classList.toggle('expandida-manual', !recolhida && escolhaManual === true);
    if (botao) {
        var texto = recolhida ? 'Expandir menu' : 'Recolher menu';
        botao.setAttribute('aria-expanded', recolhida ? 'false' : 'true');
        botao.title = texto;
        var rotulo = botao.querySelector('.visually-hidden');
        if (rotulo) rotulo.textContent = texto;
    }
}

function alternarSidebar() {
    var barra = document.getElementById('sidebar');
    if (!barra) return;
    var recolhida = !barra.classList.contains('recolhida');
    // Clique no botao e, por definicao, escolha manual.
    aplicarEstadoSidebar(recolhida, true);
    try { localStorage.setItem(CHAVE_SIDEBAR, recolhida ? 'recolhida' : 'expandida'); } catch(_) {}
    // O Leaflet mede o container so no momento em que desenha. Mudar a largura
    // da barra encolhe o mapa sem avisa-lo, e metade dele fica cinza ate o
    // proximo redraw. O atraso cobre a transicao de 0.28s da barra.
    if (mapaInstance) { setTimeout(function() { mapaInstance.invalidateSize(); }, 320); }
}

function registrarNavegacaoPorSetas() {
    // Com role="tablist" vertical, o padrao ARIA pede Cima/Baixo (e Home/End).
    // Nao havia navegacao por setas nem na versao horizontal: so Tab, que
    // percorria uma aba por vez por causa do roving tabindex.
    var lista = document.getElementById('navTabs');
    if (!lista) return;
    lista.addEventListener('keydown', function(e) {
        var abas = Array.prototype.slice.call(lista.querySelectorAll('.nav-tab'));
        var atual = abas.indexOf(document.activeElement);
        if (atual === -1) return;
        var destino;
        if (e.key === 'ArrowDown') destino = (atual + 1) % abas.length;
        else if (e.key === 'ArrowUp') destino = (atual - 1 + abas.length) % abas.length;
        else if (e.key === 'Home') destino = 0;
        else if (e.key === 'End') destino = abas.length - 1;
        else return;
        e.preventDefault();
        abas[destino].focus();
        abas[destino].click();
    });
}

function initTheme() {
    // Claro e o padrao: a paleta do app e de superficies claras, e o modo
    // escuro passou a ser a alternativa para turno noturno. Quem ja escolheu
    // um tema mantem a escolha -- so o padrao de quem nunca escolheu mudou.
    var saved = localStorage.getItem('adri-theme') || 'light';
    document.documentElement.setAttribute('data-theme', saved);
    updateThemeIcon(saved);
}

function toggleTheme() {
    var current = document.documentElement.getAttribute('data-theme');
    var next = current === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    localStorage.setItem('adri-theme', next);
    updateThemeIcon(next);
}

function updateThemeIcon(theme) {
    var sun = document.getElementById('iconSun');
    var moon = document.getElementById('iconMoon');
    var toggle = document.getElementById('btnThemeToggle');
    if (sun && moon) {
        sun.hidden = theme !== 'dark';
        moon.hidden = theme !== 'light';
    }
    if (toggle) toggle.setAttribute('aria-pressed', theme === 'light' ? 'true' : 'false');
}

function registrarAtalhosTeclado() {
    document.addEventListener('keydown', function(e) {
        if (e.ctrlKey || e.metaKey) {
            switch(e.key.toLowerCase()) {
                case 'n': e.preventDefault(); cancelarEdicao(); document.getElementById('nome').focus(); break;
                case 'f': e.preventDefault(); document.getElementById('inputPesquisa').focus(); break;
                case 'e': e.preventDefault(); enviarParaExcel(); break;
                case 'b': e.preventDefault(); fazerBackupJSON(); break;
                case 'i': e.preventDefault(); abrirModalImportar(); break;
            }
        }
    });
}

async function carregarNotificacoes() {
    try {
        var resp = await fetch('/api/notificacoes');
        var dados = await resp.json();
        window._notificacoes = dados.notificacoes || [];
        // O badge conta apenas nao lidas: e esse o sinal de "tem algo novo".
        window._notificacoesNaoLidas = dados.nao_lidas || 0;
        atualizarBadgeNotificacoes();
    } catch(_) {}
}

function atualizarBadgeNotificacoes() {
    var badge = document.getElementById('notifBadge');
    if (!badge) return;
    var naoLidas = window._notificacoesNaoLidas || 0;
    badge.hidden = naoLidas === 0;
    badge.textContent = naoLidas;
}

// Renderiza o painel sem alternar sua visibilidade. Separado de
// abrirNotificacoes() porque "Atualizar" e o marcar-como-concluida precisavam
// redesenhar a lista, e o toggle fechava o painel no lugar disso.
function renderizarNotificacoes() {
    var lista = document.getElementById('notificacoesLista');
    var contador = document.getElementById('notifCounter');
    if (!lista) return;

    var notifs = window._notificacoes || [];
    var naoLidas = notifs.filter(function(n){ return !n.lida; }).length;

    if (contador) {
        contador.textContent = naoLidas > 0
            ? naoLidas + ' nao lida(s) de ' + notifs.length
            : notifs.length + ' notificacao(es)';
    }

    var btnTodas = document.getElementById('btnMarcarTodasLidas');
    if (btnTodas) btnTodas.hidden = naoLidas === 0;

    if (notifs.length === 0) {
        lista.innerHTML = '<div class="notif-empty"><svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg><p>Nenhuma notificacao no momento</p></div>';
        return;
    }

    function renderItem(n) {
        var chave = escaparHtml(n.chave || '');
        var classes = 'notif-item notif-prioridade-' + n.prioridade + (n.lida ? ' notif-lida' : '');
        var acoes = '';
        if (n.chave) {
            acoes = n.lida
                ? '<button class="notif-acao" title="Marcar como nao lida" data-acao="naolida" data-chave="' + chave + '">' +
                  '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 4v6h6"/><path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10"/></svg></button>'
                : '<button class="notif-acao" title="Marcar como lida" data-acao="lida" data-chave="' + chave + '">' +
                  '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg></button>';
        }
        var concluir = n.entrega_id
            ? '<button class="notif-acao" title="Marcar entrega como concluida" data-acao="entrega" data-id="' + n.entrega_id + '">' +
              '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/></svg></button>'
            : '';
        return '<div class="' + classes + '">' +
            '<span class="notif-icone">' + (n.icone || '🔔') + '</span>' +
            '<div class="notif-conteudo"><div class="notif-msg">' + escaparHtml(n.msg) + '</div>' +
            (n.detalhes ? '<div class="notif-detalhes">' + escaparHtml(n.detalhes) + '</div>' : '') +
            '</div><div class="notif-acoes">' + concluir + acoes + '</div></div>';
    }

    function renderSecao(titulo, items) {
        if (items.length === 0) return '';
        return '<div class="notif-section"><div class="notif-section-title">' + titulo + ' (' + items.length + ')</div>' +
            items.map(renderItem).join('') + '</div>';
    }

    function porPrioridade(lista_, prioridade, lida) {
        return lista_.filter(function(n){ return n.prioridade === prioridade && !!n.lida === lida; });
    }

    var html = '';
    html += renderSecao('🚨 Criticas', porPrioridade(notifs, 'critica', false));
    html += renderSecao('⚠️ Altas', porPrioridade(notifs, 'alta', false));
    html += renderSecao('📋 Medias', porPrioridade(notifs, 'media', false));
    html += renderSecao('ℹ️ Informativas', porPrioridade(notifs, 'baixa', false));
    var lidas = notifs.filter(function(n){ return n.lida; });
    html += renderSecao('✓ Lidas', lidas);
    lista.innerHTML = html;
}

function abrirNotificacoes() {
    var panel = document.getElementById('notificacoesPanel');
    var botao = document.getElementById('btnNotificacoes');
    if (!panel) return;
    renderizarNotificacoes();
    panel.classList.toggle('ativo');
    if (botao) botao.setAttribute('aria-expanded', panel.classList.contains('ativo') ? 'true' : 'false');
}

async function marcarNotificacaoLida(chave, lida) {
    try {
        var resp = await fetch('/api/notificacoes/lidas', {
            method: lida ? 'POST' : 'DELETE',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ chaves: [chave] })
        });
        if (!resp.ok) throw new Error('Falha');
        await carregarNotificacoes();
        renderizarNotificacoes();
    } catch(_) { exibirToast('Erro ao atualizar notificacao.', 'error'); }
}

async function marcarTodasNotificacoesLidas() {
    try {
        var resp = await fetch('/api/notificacoes/lidas', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ todas: true })
        });
        if (!resp.ok) throw new Error('Falha');
        await carregarNotificacoes();
        renderizarNotificacoes();
        exibirToast('Todas as notificacoes foram marcadas como lidas.');
    } catch(_) { exibirToast('Erro ao marcar notificacoes.', 'error'); }
}

async function atualizarNotificacoes() {
    await carregarNotificacoes();
    renderizarNotificacoes();
}

async function marcarEntregaConcluida(entregaId) {
    try {
        var resp = await fetch('/api/entregas/' + entregaId + '/status', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ status: 'Concluida' })
        });
        if (resp.ok) {
            exibirToast('Entrega marcada como concluida!');
            await carregarNotificacoes();
            renderizarNotificacoes();
        } else {
            exibirToast('Erro ao atualizar entrega.', 'error');
        }
    } catch(_) { exibirToast('Erro ao atualizar entrega.', 'error'); }
}

function fecharNotificacoes() {
    var panel = document.getElementById('notificacoesPanel');
    if (panel) panel.classList.remove('ativo');
    var botao = document.getElementById('btnNotificacoes');
    if (botao) botao.setAttribute('aria-expanded', 'false');
}

// Paginacao da lista de clientes.
//
// Ate a versao 1.1 a tela pedia TODOS os clientes e desenhava todos de uma vez.
// Com alguns milhares de registros isso e uma pausa visivel a cada troca de
// aba; com dezenas de milhares, a aba trava -- montar dezenas de milhares de
// <tr> por concatenacao de string nao tem como sair barato.
//
// 200 por pagina cobre com folga a operacao de um dia e mantem o primeiro
// desenho instantaneo. O resto vem por demanda.
var TAMANHO_DA_PAGINA = 200;
var _clientesCarregados = [];
var _totalDeClientes = 0;
var _buscaDaPagina = '';

// Numero da carga em curso.
//
// Duas cargas podem estar em voo ao mesmo tempo -- cadastrar um cliente
// dispara uma, e digitar na busca logo em seguida dispara outra. Sem
// sequencia, a resposta da PRIMEIRA chega depois e repinta a tabela por cima
// do resultado da busca: o operador digita "Bruno", ve o resultado certo, e a
// lista completa volta sozinha meio segundo depois.
//
// A janela sempre existiu; ela ficou mais larga quando a abertura passou a
// consultar sessao e licenca antes de carregar. Foi assim que apareceu.
var _sequenciaDaCarga = 0;

async function carregarClientes() {
    var busca = (document.getElementById('inputPesquisa') || {}).value || '';
    _buscaDaPagina = busca.trim();
    _clientesCarregados = [];
    _totalDeClientes = 0;
    // Esqueleto antes da chamada: a lista mantem a altura e o operador ve que
    // algo esta em andamento, em vez de encarar a tabela vazia da consulta
    // anterior ate a resposta chegar.
    mostrarEsqueleto('tabelaClientes', 6, 5);
    return _carregarPaginaDeClientes(true, ++_sequenciaDaCarga);
}

async function carregarMaisClientes() {
    // Continua a MESMA carga: "carregar mais" acrescenta paginas a lista que
    // ja esta na tela, e nao comeca uma consulta nova.
    return _carregarPaginaDeClientes(false, _sequenciaDaCarga);
}

async function _carregarPaginaDeClientes(primeira, sequencia) {
    if (sequencia === undefined) sequencia = _sequenciaDaCarga;
    var url = API_URL + '?busca=' + encodeURIComponent(_buscaDaPagina) +
              '&limite=' + TAMANHO_DA_PAGINA +
              '&deslocamento=' + _clientesCarregados.length;
    var r = await tentarBackend(url);
    // Chegou tarde: outra carga comecou enquanto esta esperava. Renderizar
    // agora colocaria na tela o resultado de uma consulta que o operador ja
    // abandonou.
    if (sequencia !== _sequenciaDaCarga) return;
    if (r.semBackend) { carregarClientesOffline(true); return; }
    try {
        if (!r.resposta.ok) throw new Error('Falha');
        var pagina = await r.resposta.json();
        if (!Array.isArray(pagina)) pagina = [];

        var total = parseInt(r.resposta.headers.get('X-Total-Registros') || '', 10);
        _totalDeClientes = isNaN(total) ? (_clientesCarregados.length + pagina.length) : total;
        _clientesCarregados = _clientesCarregados.concat(pagina);

        // Cache para uso offline. `sincronizarCache` poda o que nao esta na
        // lista -- correto quando ela e a base inteira, destrutivo quando e
        // uma pagina: a segunda pagina seria lida como "excluida no servidor".
        // Por isso a poda so acontece quando tudo coube numa pagina so.
        if (typeof OfflineManager !== 'undefined') {
            if (_clientesCarregados.length >= _totalDeClientes) {
                OfflineManager.sincronizarCache(_clientesCarregados);
            } else {
                OfflineManager.cacheClientes(pagina);
            }
        }

        var clientes = _clientesCarregados.filter(clientePassaFiltro);
        renderizarTabela(clientes);
        _atualizarRodapeDaLista(clientes.length);
    } catch (error) {
        console.error('Erro ao carregar do servidor:', error);
        renderizarTabela([]);
        exibirToast('Erro ao carregar clientes.', 'error');
    }
}

async function carregarClientesOffline(mostrarToast) {
    try {
        if (typeof OfflineManager === 'undefined') {
            renderizarTabela([]);
            return;
        }
        var clientes = await OfflineManager.getCachedClientes();
        // Cache vazio precisa renderizar mesmo assim: sem isto a tabela ficava
        // presa nas linhas de esqueleto para sempre, sugerindo carregamento
        // eterno em vez de "offline e sem nada guardado".
        clientes = (clientes || []).filter(clientePassaFiltro);
        renderizarTabela(clientes);
        // Quem chama depois de gravar offline ja exibiu a mensagem propria
        // ("Salvo offline!"); um aviso generico aqui apagaria a informacao
        // mais util, porque o toast e um elemento so.
        if (mostrarToast) {
            exibirToast(clientes.length
                ? 'Sem conexao. Exibindo os dados guardados neste computador.'
                : 'Sem conexao e sem dados guardados neste computador.',
                clientes.length ? 'success' : 'error');
        }
    } catch (error) {
        console.error('Erro ao carregar cache offline:', error);
        renderizarTabela([]);
        exibirToast('Falha ao ler o cache offline.', 'error');
    }
}

async function registrarNovoCliente(dados) {
    var r = await tentarBackend(API_URL, { method: 'POST', headers: CABECALHOS_JSON, body: JSON.stringify(dados) });
    if (r.semBackend) {
        try {
            // O id temporario nasce ANTES de enfileirar, e vai junto na
            // pendencia. Era o elo que faltava: sem ele nada ligava a criacao
            // na fila ao registro que o operador ve na tela, e por isso uma
            // edicao feita em seguida ia contra o id negativo (404, descartada
            // em silencio) e uma exclusao deixava a criacao viva na fila (o
            // cliente reaparecia ao sincronizar).
            var novoId = -Date.now();
            dados.id = novoId;
            dados.criado_em = new Date().toISOString();
            dados._offline = true;

            await OfflineManager.savePendingAction('create', dados, novoId);
            exibirToast('Salvo offline! Sera sincronizado quando voltar online.', 'success');
            cancelarEdicao();

            var cached = await OfflineManager.getCachedClientes();
            cached.push(dados);
            await OfflineManager.cacheClientes(cached);
            carregarClientesOffline(false);
        } catch (erro) { exibirToast('Erro ao salvar offline.', 'error'); }
        return;
    }
    try {
        var resultado = await r.resposta.json();
        if (!r.resposta.ok) throw new Error(resultado.erro || 'Erro');
        exibirToast('Cliente cadastrado!');
        cancelarEdicao(); carregarClientes(); carregarDashboardGraficos();
    } catch (erro) { exibirToast('Erro ao registrar.', 'error'); }
}

async function atualizarClienteServidor(id, dados) {
    var r = await tentarBackend(API_URL+'/'+id, { method: 'PUT', headers: CABECALHOS_JSON, body: JSON.stringify(dados) });
    if (r.semBackend) {
        try {
            dados.id = id;
            if (id < 0) {
                // Cliente que so existe aqui: o servidor nem conhece o
                // registro, entao nao ha PUT a enviar. A edicao e absorvida
                // pela criacao que ainda esta na fila.
                await OfflineManager.mesclarNaCriacaoPendente(id, dados);
            } else {
                await OfflineManager.savePendingAction('update', dados);
            }
            exibirToast('Atualizacao salva offline! Sera sincronizado quando voltar online.', 'success');
            cancelarEdicao();
            // Atualizar cache local
            var cached = await OfflineManager.getCachedClientes();
            var idx = cached.findIndex(function(c) { return c.id === id; });
            if (idx !== -1) { cached[idx] = Object.assign(cached[idx], dados); }
            await OfflineManager.cacheClientes(cached);
            carregarClientesOffline(false);
        } catch (erro) { exibirToast('Erro ao salvar offline.', 'error'); }
        return;
    }
    try {
        if (!r.resposta.ok) throw new Error('Erro');
        exibirToast('Cliente atualizado!');
        cancelarEdicao(); carregarClientes(); carregarDashboardGraficos();
    } catch (erro) { exibirToast('Erro ao atualizar.', 'error'); }
}

async function excluirClienteServidor(id) {
    var confirmado = await confirmarAcao({
        titulo: 'Excluir Cliente',
        mensagem: 'Tem certeza que deseja excluir este cliente? Esta acao nao pode ser desfeita.',
        textoConfirmar: 'Excluir',
        icone: 'excluir',
        variante: 'perigo'
    });
    if (!confirmado) return;

    // ID temporario (negativo) so existe no cache local: nunca chegou ao
    // servidor, entao nao ha o que excluir la.
    var r = id < 0 ? { semBackend: true }
                   : await tentarBackend(API_URL+'/'+id, { method: 'DELETE' });
    if (r.semBackend) {
        try {
            if (id < 0) {
                // Cancela a criacao que ainda esta na fila. Limpar so o cache,
                // como antes, deixava o POST pendente intacto -- e o cliente
                // excluido reaparecia assim que a conexao voltasse.
                await OfflineManager.cancelarCriacaoPendente(id);
                exibirToast('Cliente removido antes de ser enviado.', 'success');
            } else {
                await OfflineManager.savePendingAction('delete', { id: id });
                exibirToast('Exclusao salva offline! Sera sincronizado quando voltar online.', 'success');
            }
            cancelarEdicao();
            // Remover do cache local
            var cached = await OfflineManager.getCachedClientes();
            cached = cached.filter(function(c) { return c.id !== id; });
            await OfflineManager.cacheClientes(cached);
            carregarClientesOffline(false);
        } catch (erro) { exibirToast('Erro ao salvar exclusao offline.', 'error'); }
        return;
    }
    try {
        var dados = await r.resposta.json();
        if (!r.resposta.ok) throw new Error(dados.erro || 'Erro');
        exibirToast('Cliente excluido!');
        cancelarEdicao(); carregarClientes(); carregarDashboardGraficos();
    } catch (erro) { exibirToast('Erro: ' + erro.message, 'error'); }
}


// -----------------------------------------------------------------------------
// Alteracoes offline que o servidor recusou
//
// A fila de sincronizacao apagava, sem aviso, tudo que o servidor recusasse de
// forma definitiva (4xx) ou que esgotasse as tentativas. Na pratica: o
// operador cadastrava um cliente sem conexao, o servidor recusava o CEP, e o
// cadastro simplesmente desaparecia. Ninguem ficava sabendo.
//
// Agora essas operacoes vao para uma fila de erros. Estas funcoes sao a parte
// visivel dela: um aviso na aba de clientes e um modal para reenviar ou
// descartar cada uma com conhecimento de causa.
// -----------------------------------------------------------------------------
var ACAO_LEGIVEL = { create: 'Cadastro', update: 'Edicao', delete: 'Exclusao' };

async function atualizarAvisoDePendenciasComErro() {
    var aviso = document.getElementById('avisoPendenciasComErro');
    if (!aviso || typeof OfflineManager === 'undefined') return;
    try {
        var falhas = await OfflineManager.getDeadLetters();
        if (!falhas.length) { aviso.hidden = true; return; }
        aviso.hidden = false;
        var detalhe = document.getElementById('avisoPendenciasDetalhe');
        if (detalhe) {
            detalhe.textContent = falhas.length === 1
                ? '1 alteracao feita offline foi recusada pelo servidor.'
                : falhas.length + ' alteracoes feitas offline foram recusadas pelo servidor.';
        }
    } catch (erro) {
        console.error('Nao foi possivel ler a fila de erros:', erro);
    }
}

async function abrirPendenciasComErro() {
    var lista = document.getElementById('listaPendenciasComErro');
    if (!lista) return;
    var falhas = await OfflineManager.getDeadLetters();

    if (!falhas.length) {
        lista.innerHTML = '<div class="empty-state"><p>Nenhuma alteracao pendente de correcao.</p></div>';
    } else {
        lista.innerHTML = falhas.map(function(f) {
            var nome = (f.dados && f.dados.nome) ? f.dados.nome : ('registro #' + (f.dados && f.dados.id));
            return '<div class="pendencia-erro">' +
                '<div class="pendencia-erro-cabecalho">' +
                    '<span class="pendencia-erro-nome">' +
                        escaparHtml(ACAO_LEGIVEL[f.action] || f.action) + ': ' + escaparHtml(String(nome)) +
                    '</span>' +
                    '<span class="pendencia-erro-quando">' + escaparHtml(formatarQuando(f.timestamp)) + '</span>' +
                '</div>' +
                '<div class="pendencia-erro-motivo">' + escaparHtml(f.motivo || 'Motivo nao registrado') + '</div>' +
                '<div class="pendencia-erro-acoes">' +
                    '<button type="button" class="btn btn-primary btn-sm" data-reenviar="' + f.id + '">Tentar de novo</button>' +
                    '<button type="button" class="btn btn-perigo btn-sm" data-descartar="' + f.id + '">Descartar</button>' +
                '</div>' +
            '</div>';
        }).join('');
    }
    abrirModal('modalPendenciasComErro');
}

function formatarQuando(iso) {
    if (!iso) return '';
    var data = new Date(iso);
    return isNaN(data.getTime()) ? '' : data.toLocaleString('pt-BR');
}

async function _acaoNaPendenciaComErro(elemento) {
    var idReenviar = elemento.getAttribute('data-reenviar');
    var idDescartar = elemento.getAttribute('data-descartar');

    if (idReenviar) {
        await OfflineManager.reenviarDeadLetter(Number(idReenviar));
        exibirToast('Reenviando...');
    } else if (idDescartar) {
        var confirmado = await confirmarAcao({
            titulo: 'Descartar alteracao',
            mensagem: 'Esta alteracao sera perdida definitivamente. Deseja continuar?',
            textoConfirmar: 'Descartar',
            icone: 'excluir',
            variante: 'perigo'
        });
        if (!confirmado) return;
        await OfflineManager.descartarDeadLetter(Number(idDescartar));
    } else {
        return;
    }

    await abrirPendenciasComErro();
    await atualizarAvisoDePendenciasComErro();
    carregarClientes();
}


// -----------------------------------------------------------------------------
// Estados de tabela
//
// Vazio e carregando deixaram de ser uma celula com texto solto: sao blocos
// com forma propria, definidos em `.empty-state` e `.skeleton-row` no CSS.
// O esqueleto importa mais do que parece -- ele segura a altura da lista, e
// sem ele o conteudo abaixo salta quando os dados chegam.
// -----------------------------------------------------------------------------
var ICONE_VAZIO = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><circle cx="11" cy="11" r="7"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>';

function linhaEstadoVazio(colunas, titulo, detalhe) {
    return '<tr><td colspan="' + colunas + '">' +
        '<div class="empty-state">' +
        '<div class="empty-state-icon" aria-hidden="true">' + ICONE_VAZIO + '</div>' +
        '<h3>' + escaparHtml(titulo) + '</h3>' +
        '<p>' + escaparHtml(detalhe) + '</p>' +
        '</div></td></tr>';
}

function mostrarEsqueleto(idTabela, colunas, linhas) {
    var tbody = document.getElementById(idTabela);
    if (!tbody) return;
    var celulas = new Array(colunas + 1).join('<td>&nbsp;</td>');
    var html = '';
    for (var i = 0; i < (linhas || 5); i++) html += '<tr class="skeleton-row">' + celulas + '</tr>';
    tbody.innerHTML = html;
}

function _atualizarRodapeDaLista(visiveis) {
    var rodape = document.getElementById('rodapeClientes');
    var contagem = document.getElementById('contagemClientes');
    var botao = document.getElementById('btnCarregarMaisClientes');
    if (!rodape || !contagem || !botao) return;

    var faltam = _totalDeClientes - _clientesCarregados.length;
    if (faltam <= 0 && _totalDeClientes <= TAMANHO_DA_PAGINA) {
        // Cabe tudo numa pagina: o rodape so ocuparia espaco.
        rodape.hidden = true;
        return;
    }

    rodape.hidden = false;
    // Saber que existem 1.240 registros e ver 200 e diferente de achar que ha
    // 200. A contagem fica visivel enquanto houver mais de uma pagina.
    contagem.textContent = 'Mostrando ' + visiveis + ' de ' + _totalDeClientes +
                           (visiveis !== _clientesCarregados.length
                              ? ' (filtro aplicado sobre ' + _clientesCarregados.length + ' carregados)'
                              : '');
    botao.hidden = faltam <= 0;
    botao.textContent = faltam > 0
        ? 'Carregar mais ' + Math.min(faltam, TAMANHO_DA_PAGINA)
        : 'Carregar mais';
}

function renderizarTabela(clientes) {
    var tabela = document.getElementById('tabelaClientes');
    if (!tabela) return;
    if (!Array.isArray(clientes)) clientes = [];
    if (clientes.length === 0) {
        tabela.innerHTML = linhaEstadoVazio(6, 'Nenhum cliente encontrado',
            'Ajuste a busca ou os filtros, ou cadastre um cliente no formulario acima.');
        return;
    }
    var html = '';
    clientes.forEach(function(c) {
        var badgeClass = (c.entrega_retirada || 'Entrega') === 'Retirada' ? 'badge-retirada' : 'badge-entrega';
        var idSeguro = escaparHtml('' + c.id);
        var nome = escaparHtml(c.nome || '');
        var cidade = escaparHtml(c.cidade || '');
        var bairro = escaparHtml(c.bairro || '');
        html +=
            '<tr>' +
            // Sem `aria-label` o leitor de tela anuncia so "caixa de selecao":
            // numa lista de 200 linhas, nenhuma delas identificavel.
            '<td class="col-checkbox"><input type="checkbox" class="client-checkbox" value="'+idSeguro+'" aria-label="Selecionar '+nome+'"></td>' +
            // `title` porque a coluna trunca com reticencia: o nome completo
            // continua alcancavel sem abrir o cadastro.
            '<td class="col-nome" title="'+nome+'"><strong>'+nome+'</strong></td>' +
            '<td class="col-cidade" title="'+cidade+'">'+cidade+'</td>' +
            '<td class="col-bairro" title="'+bairro+'">'+bairro+'</td>' +
            '<td class="col-tipo"><span class="'+badgeClass+'">'+escaparHtml(c.entrega_retirada||'Entrega')+'</span></td>' +
            '<td class="col-acoes"><div class="tabela-acoes">' +
            '<button type="button" class="btn btn-secundario btn-sm" data-action="editar" data-id="'+idSeguro+'" data-nome="'+nome+'" data-cep="'+escaparHtml(c.cep||'')+'" data-rua="'+escaparHtml(c.rua||'')+'" data-bairro="'+bairro+'" data-cidade="'+cidade+'" data-tipo="'+escaparHtml(c.entrega_retirada||'Entrega')+'" data-obs="'+escaparHtml(c.observacoes||'')+'">Editar</button>' +
            '<button type="button" class="btn btn-perigo btn-sm" data-action="excluir" data-id="'+idSeguro+'">Excluir</button>' +
            '</div></td>' +
            '</tr>';
    });
    tabela.innerHTML = html;
}

function editarCliente(id, nome, cep, rua, bairro, cidade, entrega_retirada, observacoes) {
    document.getElementById('clienteId').value = String(id);
    document.getElementById('nome').value = nome;
    document.getElementById('cep').value = cep;
    document.getElementById('rua').value = rua;
    document.getElementById('bairro').value = bairro;
    document.getElementById('cidade').value = cidade;
    document.getElementById('entregaRetirada').value = entrega_retirada || 'Entrega';
    document.getElementById('observacoes').value = observacoes || '';
    document.getElementById('btnSalvar').innerText = 'Atualizar Cliente';
    document.getElementById('btnCancelar').style.display = 'inline-block';
    document.getElementById('formTitleText').textContent = 'Editar informacoes';
    var editIcon = document.getElementById('editIcon');
    if (editIcon) editIcon.style.display = 'inline';
    window.scrollTo({ top: 0, behavior: 'smooth' });
    atualizarContadorObs();
}

function cancelarEdicao() {
    var form = document.getElementById('clienteForm');
    if (form) form.reset();
    document.getElementById('clienteId').value = '';
    document.getElementById('btnSalvar').innerText = 'Salvar Cliente';
    document.getElementById('btnCancelar').style.display = 'none';
    document.getElementById('formTitleText').textContent = 'Cadastro de Cliente';
    var editIcon = document.getElementById('editIcon');
    if (editIcon) editIcon.style.display = 'none';
    atualizarContadorObs();
}

function initObservacoesCounter() {
    var obs = document.getElementById('observacoes');
    if (obs) obs.addEventListener('input', atualizarContadorObs);
}

function atualizarContadorObs() {
    var obs = document.getElementById('observacoes');
    var counter = document.getElementById('obsCount');
    if (obs && counter) counter.textContent = obs.value.length + '/1000';
}

function toggleModoSelecao() {
    if (saindoSelecao) return;
    modoSelecaoAtivo = !modoSelecaoAtivo;
    var txt = document.getElementById('txtBtnSelecao');
    var btn = document.getElementById('btnModoSelecao');
    if (modoSelecaoAtivo) {
        if (btn) btn.classList.add('ativo');
        if (btn) btn.setAttribute('aria-pressed', 'true');
        if (txt) txt.innerText = 'Sair da Selecao';
        document.body.classList.add('modo-selecao-ativo');
    } else {
        if (btn) btn.classList.remove('ativo');
        if (btn) btn.setAttribute('aria-pressed', 'false');
        if (txt) txt.innerText = 'Selecionar Clientes';
        saindoSelecao = true;
        document.body.classList.add('saindo-selecao');
        setTimeout(function() {
            document.body.classList.remove('modo-selecao-ativo', 'saindo-selecao');
            saindoSelecao = false;
            document.querySelectorAll('.client-checkbox').forEach(function(cb){ cb.checked = false; });
            var selectAll = document.getElementById('selectAll');
            if (selectAll) { selectAll.checked = false; selectAll.indeterminate = false; }
        }, 300);
    }
}

function toggleFiltro() {
    var dropdown = document.getElementById('filtroDropdown');
    var btnFiltro = document.getElementById('btnFiltro');
    if (!dropdown) return;
    if (dropdown.classList.contains('ativo')) {
        dropdown.classList.remove('ativo');
        if (btnFiltro) { btnFiltro.classList.remove('ativo'); btnFiltro.setAttribute('aria-expanded', 'false'); }
    } else {
        carregarCidadesParaFiltro();
        dropdown.classList.add('ativo');
        if (btnFiltro) { btnFiltro.classList.add('ativo'); btnFiltro.setAttribute('aria-expanded', 'true'); }
    }
}

async function carregarCidadesParaFiltro() {
    try {
        var resp = await fetch(API_URL+'?busca=');
        var clientes = await resp.json();
        var cidadesSet = new Set();
        clientes.forEach(function(c){ if (c.cidade && c.cidade.trim()) cidadesSet.add(c.cidade.trim()); });
        var container = document.getElementById('filtroCidadesContainer');
        if (!container) return;
        container.innerHTML = '';
        Array.from(cidadesSet).sort().forEach(function(cidade) {
            var label = document.createElement('label');
            label.className = 'filtro-cidade-item';
            label.innerHTML = '<input type="checkbox" name="filtroCidade" value="'+escaparHtml(cidade)+'" checked><span>'+escaparHtml(cidade)+'</span>';
            container.appendChild(label);
        });
    } catch(_) {}
}

// O dropdown fecha ao aplicar, entao sem este indicador a lista fica filtrada
// sem nenhum sinal na tela -- o operador ve menos clientes do que cadastrou e
// nao tem como saber por que. O rotulo e o contador ja existiam no HTML e
// nunca eram tocados pelo JS.
function atualizarIndicadorFiltro() {
    var rotulo = document.getElementById('txtBtnFiltro');
    var contador = document.getElementById('badgeFiltroCount');
    // Os dois tipos marcados sao o estado inicial: nao restringem nada.
    var tiposRestringem = filtrosAtivos.tipos.length !== 2;
    var quantidade = filtrosAtivos.cidades.length + (tiposRestringem ? 1 : 0);

    if (rotulo) rotulo.textContent = quantidade ? 'Filtrando' : 'Filtrar';
    if (contador) {
        contador.textContent = quantidade;
        contador.hidden = quantidade === 0;
    }
}

function aplicarFiltros() {
    filtrosAtivos.tipos = Array.from(document.querySelectorAll('input[name="filtroTipo"]:checked')).map(function(cb){ return cb.value; });
    filtrosAtivos.cidades = Array.from(document.querySelectorAll('input[name="filtroCidade"]:checked')).map(function(cb){ return cb.value; });
    var dd = document.getElementById('filtroDropdown'); if(dd) dd.classList.remove('ativo');
    var bf = document.getElementById('btnFiltro'); if(bf) { bf.classList.remove('ativo'); bf.setAttribute('aria-expanded', 'false'); }
    atualizarIndicadorFiltro();
    carregarClientes();
}

function limparFiltros() {
    filtrosAtivos = { tipos: ['Entrega', 'Retirada'], cidades: [] };
    document.querySelectorAll('input[name="filtroTipo"]').forEach(function(cb){ cb.checked = true; });
    document.querySelectorAll('input[name="filtroCidade"]').forEach(function(cb){ cb.checked = true; });
    atualizarIndicadorFiltro();
    carregarClientes();
}

function clientePassaFiltro(cliente) {
    var tipo = cliente.entrega_retirada || 'Entrega';
    if (filtrosAtivos.tipos.length > 0 && filtrosAtivos.tipos.indexOf(tipo) === -1) return false;
    if (filtrosAtivos.cidades.length > 0) {
        var cidade = (cliente.cidade || '').trim();
        if (filtrosAtivos.cidades.indexOf(cidade) === -1) return false;
    }
    return true;
}

async function sugerirBairro() {
    var cepEl = document.getElementById('cep');
    var cep = (cepEl ? cepEl.value : '').replace('-','');
    if (cep.length !== 8 || !/^\d+$/.test(cep)) { exibirToast('Digite um CEP valido (8 digitos).', 'error'); return; }
    exibirToast('Buscando dados do CEP...');
    try {
        var resp = await fetch('/api/ia/sugestao-bairro', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ cep: cep }) });
        var dados = await resp.json();
        if (resp.ok && dados.bairro) {
            if (dados.bairro) document.getElementById('bairro').value = dados.bairro;
            if (dados.cidade) document.getElementById('cidade').value = dados.cidade;
            if (dados.rua) document.getElementById('rua').value = dados.rua;
            exibirToast('Dados preenchidos via ' + (dados.fonte || 'IA') + '!');
        } else { exibirToast(dados.erro || 'Nao foi possivel buscar dados.', 'error'); }
    } catch(_) { exibirToast('Erro ao consultar CEP.', 'error'); }
}

// -----------------------------------------------------------------------------
// Backup
//
// Duas correcoes moram aqui.
//
// 1. A URL estava errada: as rotas vivem no blueprint de clientes, sob o
//    prefixo /api/clientes. O caminho antigo devolvia 404.
//
// 2. `window.open` NAO consegue observar o resultado da requisicao -- e por
//    isso o codigo antigo anunciava "Backup iniciado!" mesmo quando a resposta
//    era 404. O operador lia a confirmacao e ficava sem backup nenhum, que e
//    pior do que nao ter a funcao. Com `fetch` o status e verificavel, entao
//    o aviso passa a corresponder ao que de fato aconteceu.
// -----------------------------------------------------------------------------
function _nomeDoAnexo(resposta, alternativo) {
    var cabecalho = resposta.headers.get('Content-Disposition') || '';
    var achado = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(cabecalho);
    return achado ? decodeURIComponent(achado[1]) : alternativo;
}

// Mensagem curta e acionavel por status. O texto cru do servidor nao serve
// para um toast: o 404 padrao do Flask sozinho tem 120 caracteres de prosa
// sobre conferir a URL, que nao diz nada ao operador.
function _motivoDaFalha(resposta, detalhe) {
    if (resposta.status === 404) return 'rota de backup nao encontrada no servidor';
    if (resposta.status === 401 || resposta.status === 403) return 'sem permissao';
    if (resposta.status >= 500) return 'o servidor falhou ao gerar o arquivo';
    // Mensagem propria da API (curta, na chave `erro`) vale mais que o status.
    if (detalhe && detalhe.length <= 90) return detalhe;
    return 'o servidor respondeu ' + resposta.status;
}

async function baixarArquivo(url, nomeAlternativo, mensagemSucesso) {
    try {
        var resposta = await fetch(url);
        if (!resposta.ok) {
            var detalhe = '';
            try { detalhe = (await resposta.json()).erro || ''; } catch (_) {}
            throw new Error(_motivoDaFalha(resposta, detalhe));
        }
        var blob = await resposta.blob();
        var endereco = URL.createObjectURL(blob);
        var link = document.createElement('a');
        link.href = endereco;
        link.download = _nomeDoAnexo(resposta, nomeAlternativo);
        document.body.appendChild(link);
        link.click();
        link.remove();
        // Sem o revoke o blob fica retido em memoria ate a aba fechar -- e um
        // backup do banco inteiro nao e pequeno.
        setTimeout(function() { URL.revokeObjectURL(endereco); }, 1000);
        exibirToast(mensagemSucesso);
    } catch (erro) {
        exibirToast('Backup nao concluido: ' + erro.message, 'error');
    }
}

function _carimboDeData() {
    return new Date().toISOString().slice(0, 10).replace(/-/g, '');
}

function fazerBackupJSON() {
    baixarArquivo('/api/backup/json',
        'backup_adri_poltronas_' + _carimboDeData() + '.json',
        'Backup JSON salvo.');
}

async function fazerBackupSQLite() {
    // O arquivo e o banco inteiro, com todos os clientes e lancamentos. Vale
    // uma confirmacao antes de ele sair da maquina.
    var confirmado = await confirmarAcao({
        titulo: 'Baixar o banco de dados',
        mensagem: 'O arquivo contem toda a base: clientes, pagamentos e historico. '
                + 'Guarde em local seguro.',
        textoConfirmar: 'Baixar',
        icone: 'alerta',
        variante: 'atencao'
    });
    if (!confirmado) return;
    baixarArquivo('/api/backup/sqlite',
        'backup_adri_poltronas_' + _carimboDeData() + '.db',
        'Backup do banco salvo.');
}

// -----------------------------------------------------------------------------
// Restauracao de copia
//
// As copias eram criadas -- antes de cada migration e uma por dia -- e nao
// havia caminho de volta pela interface: recuperar exigia fechar o app, achar
// a pasta em %APPDATA%, entender o nome dos arquivos e sobrescrever o banco na
// mao. Ninguem descobre que o backup nao presta antes de precisar dele.
// -----------------------------------------------------------------------------
var MOTIVO_LEGIVEL = {
    'pre-migracao': 'antes de atualizar',
    'diario': 'copia do dia'
};

async function abrirModalRestaurar() {
    var lista = document.getElementById('listaCopias');
    if (!lista) return;
    lista.innerHTML = '<div class="empty-state"><p>Carregando copias...</p></div>';
    abrirModal('modalRestaurar');

    var r = await tentarBackend('/api/backup/copias');
    if (r.semBackend) {
        lista.innerHTML = '<div class="empty-state"><p>Sem conexao com o servidor local.</p></div>';
        return;
    }
    var dados = await r.resposta.json();
    var pasta = document.getElementById('modalRestaurarPasta');
    if (pasta) pasta.textContent = 'Pasta das copias: ' + (dados.pasta || '');

    if (!dados.copias || !dados.copias.length) {
        lista.innerHTML = '<div class="empty-state"><p>Nenhuma copia disponivel ainda.</p></div>';
        return;
    }

    lista.innerHTML = dados.copias.map(function(c) {
        return '<div class="pendencia-erro">' +
            '<div class="pendencia-erro-cabecalho">' +
                '<span class="pendencia-erro-nome">' + escaparHtml(c.criado_em) + '</span>' +
                '<span class="pendencia-erro-quando">' + formatarTamanho(c.bytes) + '</span>' +
            '</div>' +
            '<div class="pendencia-erro-quando">' +
                escaparHtml(MOTIVO_LEGIVEL[c.motivo] || c.motivo) + '</div>' +
            '<div class="pendencia-erro-acoes">' +
                '<button type="button" class="btn btn-perigo btn-sm" data-restaurar="' +
                    escaparHtml(c.arquivo) + '">Restaurar esta</button>' +
            '</div>' +
        '</div>';
    }).join('');
}

function formatarTamanho(bytes) {
    if (!bytes) return '';
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return Math.round(bytes / 1024) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

async function restaurarCopia(arquivo) {
    var confirmado = await confirmarAcao({
        titulo: 'Restaurar o banco',
        mensagem: 'Tudo que foi registrado depois desta copia sera perdido. '
                + 'O estado atual sera guardado como uma nova copia antes da troca. '
                + 'Depois de restaurar, feche e abra o aplicativo.',
        textoConfirmar: 'Restaurar',
        textoCancelar: 'Voltar',
        icone: 'alerta',
        variante: 'perigo'
    });
    if (!confirmado) return;

    try {
        var resp = await fetch('/api/backup/restaurar', {
            method: 'POST',
            headers: CABECALHOS_JSON,
            body: JSON.stringify({ arquivo: arquivo })
        });
        var dados = await resp.json();
        if (!resp.ok) throw new Error(dados.erro || 'Erro');
        fecharModal('modalRestaurar');
        // Sem recarregar, as telas ja abertas seguem mostrando os dados de
        // antes -- e uma edicao feita sobre elas gravaria por cima do que
        // acabou de ser restaurado.
        exibirToast(dados.mensagem + ' Recarregando...', 'success');
        setTimeout(function() { window.location.reload(); }, 2500);
    } catch (e) {
        exibirToast('Nao foi possivel restaurar: ' + e.message, 'error');
    }
}

function abrirModalImportar() {
    var modal = document.getElementById('modalImportar');
    if (modal) {
        abrirModal(modal);
        document.getElementById('inputArquivoImportar').value = '';
        var res = document.getElementById('importarResultado');
        if (res) { res.style.display = 'none'; res.innerHTML = ''; }
    }
}

async function executarImportacao() {
    var input = document.getElementById('inputArquivoImportar');
    var resultado = document.getElementById('importarResultado');
    if (!input || !input.files.length) { exibirToast('Selecione um arquivo.', 'error'); return; }
    var formData = new FormData();
    formData.append('arquivo', input.files[0]);
    try {
        var resp = await fetch('/api/clientes/importar', { method: 'POST', body: formData });
        var dados = await resp.json();
        if (!resp.ok) throw new Error(dados.erro || 'Erro');
        if (resultado) {
            resultado.className = 'importar-resultado importar-ok';
            resultado.innerHTML = '<strong>Importacao concluida.</strong><br>Importados: '+dados.sucessos+'<br>Duplicados: '+dados.duplicados+'<br>Erros: '+dados.erros;
        }
        exibirToast(dados.sucessos + ' clientes importados!');
        carregarClientes();
        carregarDashboardGraficos();
    } catch(e) {
        if (resultado) {
            resultado.className = 'importar-resultado importar-erro';
            resultado.innerHTML = '<strong>Erro:</strong> '+escaparHtml(e.message);
        }
        exibirToast('Erro na importacao.', 'error');
    }
}

async function checarLoginExistente() {
    try {
        var resp = await fetch('/api/auth/status');
        var status = await resp.json();
        if (status.logado) {
            atualizarVisualBotaoConexao(status.conta);
            if (intervaloChecagem) { clearInterval(intervaloChecagem); intervaloChecagem = null; }
            // A ordem importa: some o painel, e so entao os dados entram numa
            // tela que ja voltou a mostrar conteudo.
            registrarSessaoPresente();
            liberarDadosSeOsPortoesAbrirem();
            return true;
        }
        resetarVisualBotaoConexao();
        registrarSessaoAusente();
        // O backend so devolve este motivo quando havia uma sessao que nao
        // pode mais ser renovada -- vale avisar, porque a tela acabou de
        // mudar de "Conectado" para "Conectar" sem o operador ter feito nada.
        if (status.motivo === 'sessao_expirada') {
            exibirToast('Sessao Microsoft expirada. Reconecte para exportar planilhas.', 'error');
        }
    } catch(_) {}
    return false;
}

// O botao de conexao mora na topbar, ao lado do estado da rede, e ali o espaco
// e curto. O rotulo carrega o essencial -- quem esta conectado -- e o `title`
// carrega o resto: a conta inteira, que num e-mail longo nao caberia.
function atualizarVisualBotaoConexao(conta) {
    var btnConectar = document.getElementById('btnConectarMicrosoft');
    var btnEnviar = document.getElementById('btnEnviarExcel');
    var txtConectar = document.getElementById('txtBtnConectar');
    if (btnConectar) {
        btnConectar.classList.add('conectado');
        btnConectar.classList.remove('carregando');
        btnConectar.title = 'Conectado como ' + conta + '. Clique para desconectar.';
    }
    if (txtConectar) txtConectar.innerText = conta.split('@')[0];
    if (btnEnviar) btnEnviar.disabled = false;
}

function resetarVisualBotaoConexao() {
    var btnConectar = document.getElementById('btnConectarMicrosoft');
    var btnEnviar = document.getElementById('btnEnviarExcel');
    var txtConectar = document.getElementById('txtBtnConectar');
    if (btnConectar) {
        btnConectar.classList.remove('conectado');
        btnConectar.title = 'Conectar conta Microsoft';
    }
    if (txtConectar) txtConectar.innerText = 'Conectar';
    if (btnEnviar) btnEnviar.disabled = true;
}

async function conectarMicrosoft() {
    var estaLogado = await checarLoginExistente();
    if (estaLogado) {
        var confirmado = await confirmarAcao({
            titulo: 'Desconectar Conta',
            mensagem: 'Sua conta Microsoft sera desconectada e o envio de planilhas para o OneDrive deixara de funcionar ate voce reconectar.',
            textoConfirmar: 'Desconectar',
            icone: 'desconectar',
            variante: 'atencao'
        });
        if (confirmado) { await desconectarMicrosoft(); }
        return;
    }
    try { exibirToast('Abrindo login...'); await fetch('/api/auth/login'); if(!intervaloChecagem) intervaloChecagem = setInterval(checarLoginExistente, 1500); } catch(_) { exibirToast('Falha ao iniciar login.', 'error'); }
}

async function desconectarMicrosoft() {
    try {
        var resp = await fetch('/api/auth/logout', { method: 'POST' });
        if (resp.ok) {
            resetarVisualBotaoConexao();
            // Sem isto a tela ficaria com o cadastro do operador anterior
            // ate a proxima requisicao voltar 401 -- dado visivel depois de
            // desconectar e exatamente o que a desconexao deveria encerrar.
            _dadosJaCarregados = false;
            registrarSessaoAusente();
            exibirToast('Desconectado da Microsoft.');
        }
    } catch(_) { exibirToast('Erro ao desconectar.', 'error'); }
}

async function enviarParaExcel() {
    var estaLogado = await checarLoginExistente();
    if (!estaLogado) { exibirToast('Conecte-se a Microsoft primeiro.', 'error'); return; }
    var idsParaEnviar = [];
    if (modoSelecaoAtivo) {
        idsParaEnviar = Array.from(document.querySelectorAll('.client-checkbox:checked')).map(function(cb){ return parseInt(cb.value); });
        if (idsParaEnviar.length === 0) { exibirToast('Selecione ao menos um cliente.', 'error'); return; }
    } else {
        var busca = ((document.getElementById('inputPesquisa')||{}).value||'').trim();
        var resp = await fetch(API_URL+'?busca='+encodeURIComponent(busca));
        var todos = await resp.json();
        idsParaEnviar = todos.filter(clientePassaFiltro).map(function(c){ return c.id; });
        if (idsParaEnviar.length === 0) { exibirToast('Nenhum cliente encontrado.', 'error'); return; }
    }
    window._confirmNomeCallback = function() {
        var nome = (document.getElementById('inputNomeArquivo')||{}).value || 'Clientes_AdriPoltronas';
        enviarExcelComNome(idsParaEnviar, nome);
    };
    abrirModal('modalNomeArquivo');
}

async function enviarExcelComNome(ids, nomeArquivo) {
    var btnEnviar = document.getElementById('btnEnviarExcel');
    // A sessao pode cair durante o envio; nesse caso o botao NAO volta a ficar
    // habilitado no `finally`, senao a tela continuaria oferecendo uma acao
    // que o backend ja nao aceita.
    var sessaoCaiu = false;
    try {
        if (btnEnviar) { btnEnviar.disabled = true; btnEnviar.classList.add('carregando'); }
        var resp = await fetch('/api/excel/enviar', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ids: ids, nome_arquivo: nomeArquivo }) });
        var dados = await resp.json();
        if (resp.status === 401) {
            sessaoCaiu = true;
            resetarVisualBotaoConexao();
            exibirToast('Sessao Microsoft encerrada. Clique em "Conectar", no topo da tela, para reconectar.', 'error');
            return;
        }
        if (!resp.ok) throw new Error(dados.erro || 'Falha');
        exibirToast('Planilha enviada para o OneDrive.');
    } catch(e) { exibirToast('Erro: ' + e.message, 'error'); }
    finally {
        if (btnEnviar) {
            btnEnviar.classList.remove('carregando');
            btnEnviar.disabled = sessaoCaiu;
        }
    }
}

// -----------------------------------------------------------------------------
// Mapa de Clientes (Leaflet/OpenStreetMap)
// -----------------------------------------------------------------------------
var mapaInstance = null;
var mapaMarcadores = [];
// -----------------------------------------------------------------------------
// Cache de geocodificacao
//
// A Nominatim exige 1 requisicao por segundo, e o mapa geocodifica cliente a
// cliente em serie. Com o cache apenas em memoria, TUDO era refeito a cada
// reinicio do app -- com 200 clientes, ~4 minutos de espera toda vez que o
// mapa era aberto pela primeira vez na sessao. localStorage torna o custo
// pago uma unica vez por maquina.
// -----------------------------------------------------------------------------
var CHAVE_GEOCACHE = 'adri-geocache';
var _geocacheCoords = carregarGeocache();
var _mapaCarregando = false;
// Incrementado a cada carregamento do mapa: um carregamento antigo que ainda
// esteja no meio da fila de 1,1 s por cliente percebe que ficou obsoleto e
// para, em vez de seguir desenhando marcadores sobre o mapa novo.
var _geracaoMapa = 0;

function carregarGeocache() {
    try {
        return JSON.parse(localStorage.getItem(CHAVE_GEOCACHE) || '{}') || {};
    } catch (e) {
        return {};
    }
}

function guardarGeocache() {
    try {
        localStorage.setItem(CHAVE_GEOCACHE, JSON.stringify(_geocacheCoords));
    } catch (e) {
        // Cota estourada ou storage bloqueado: o cache em memoria continua
        // valendo para esta sessao, entao nao ha o que fazer aqui.
        console.warn('[geocache] nao foi possivel persistir:', e);
    }
}

// -----------------------------------------------------------------------------
// Aparencia do mapa
//
// A base segue sendo a do OpenStreetMap, e o tema escuro sai de um filtro CSS
// aplicado ao painel de tiles (ver .leaflet-tile-pane no style.css).
//
// A alternativa obvia seria uma base ja escura de terceiro. A CARTO foi
// testada e hoje devolve os tiles com marca d'agua "API KEY REQUIRED" --
// respondendo HTTP 200, entao so da para perceber olhando a imagem. Stadia e
// Mapbox tambem exigem chave. Filtrar no cliente evita cadastro, chave para
// guardar, host novo na CSP e um ponto a mais de falha, e reaproveita os
// tiles que ja funcionam aqui.
// -----------------------------------------------------------------------------
// Zoom de bairro: perto o bastante para reconhecer a rua, longe o
// bastante para situar o cliente na cidade.
var ZOOM_CLIENTE_UNICO = 14;
var URL_TILES_MAPA = 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png';
var ATRIBUICAO_MAPA = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>';

// Marcador como ponto-sinal, e nao como alfinete: no zoom de cidade dezenas
// de alfinetes viram uma parede de icones, enquanto pontos luminosos deixam
// ler a densidade. As cores sao as mesmas dos badges de Entrega/Retirada
// usados no resto do app, entao o mapa nao inventa uma legenda propria.
function iconeCliente(tipo) {
    var variante = tipo === 'Retirada' ? 'retirada' : 'entrega';
    return L.divIcon({
        className: 'marcador-cliente',
        html: '<span class="ponto-sinal ponto-' + variante + '">'
            + '<i class="ponto-halo"></i><i class="ponto-nucleo"></i></span>',
        iconSize: [16, 16],
        iconAnchor: [8, 8],
        popupAnchor: [0, -12]
    });
}


function initMapa() {
    var mapContainer = document.getElementById('mapaClientes');
    if (!mapContainer || mapaInstance) return;
    mapaInstance = L.map('mapaClientes', {
        center: [-15.7801, -47.9292],
        zoom: 4,
        zoomControl: true
    });
    L.tileLayer(URL_TILES_MAPA, {
        attribution: ATRIBUICAO_MAPA,
        maxZoom: 19
    }).addTo(mapaInstance);
    setTimeout(function() { mapaInstance.invalidateSize(); }, 300);
}

async function geocodificarCliente(cliente) {
    var cepLimpo = (cliente.cep || '').replace(/\D/g, '');
    // Cache key usa endereço completo para precisão
    var partes = [cliente.rua, cliente.bairro, cliente.cidade].filter(Boolean);
    var cacheKey = partes.join(',').trim().toLowerCase() || cepLimpo;
    if (!cacheKey) return null;
    if (_geocacheCoords[cacheKey]) return _geocacheCoords[cacheKey];

    // Passo 1: Geocodificar endereço completo via Nominatim (mais preciso)
    var partesEndereco = [];
    if (cliente.rua) partesEndereco.push(cliente.rua);
    if (cliente.bairro) partesEndereco.push(cliente.bairro);
    if (cliente.cidade) partesEndereco.push(cliente.cidade);
    var uf = '';
    if (cepLimpo.length === 8) {
        try {
            var viaResp = await fetch('https://viacep.com.br/ws/' + cepLimpo + '/json/');
            var viaDados = await viaResp.json();
            if (!viaDados.erro) {
                uf = viaDados.uf || '';
                // Se não tem rua/bairro no cadastro, usar dados do ViaCEP
                if (!cliente.rua && viaDados.logradouro) partesEndereco.unshift(viaDados.logradouro);
                if (!cliente.bairro && viaDados.bairro) partesEndereco.splice(1, 0, viaDados.bairro);
            }
        } catch(e) { console.warn('ViaCEP falhou:', cepLimpo, e); }
    }
    if (uf) partesEndereco.push(uf);
    partesEndereco.push('Brasil');

    // Tentar endereço completo primeiro
    if (partesEndereco.length > 2) {
        var queryCompleta = partesEndereco.join(', ');
        await new Promise(function(r) { setTimeout(r, 1100); });
        var coords = await geocodificarCidade(queryCompleta);
        if (coords) { _geocacheCoords[cacheKey] = coords; guardarGeocache(); return coords; }
    }

    // Passo 2: Fallback - apenas cidade + UF
    if (cliente.cidade && cliente.cidade.trim()) {
        await new Promise(function(r) { setTimeout(r, 1100); });
        var queryCidade = cliente.cidade.trim() + (uf ? ', ' + uf : '') + ', Brasil';
        var coords = await geocodificarCidade(queryCidade);
        if (coords) { _geocacheCoords[cacheKey] = coords; guardarGeocache(); return coords; }
    }
    return null;
}

async function geocodificarCidade(query) {
    try {
        var resp = await fetch('https://nominatim.openstreetmap.org/search?format=json&limit=1&q=' + encodeURIComponent(query) + '&accept-language=pt-BR', {
            headers: { 'Accept': 'application/json', 'User-Agent': 'AdriPoltronas/1.0 (contato@adripoltronas.com.br)' }
        });
        var dados = await resp.json();
        if (dados.length > 0) {
            return { lat: parseFloat(dados[0].lat), lon: parseFloat(dados[0].lon) };
        }
    } catch(e) { console.warn('Nominatim falhou:', query, e); }
    return null;
}
// -----------------------------------------------------------------------------
// Pagamentos -- area desativada nesta versao
//
// O registro, a listagem, a emissao de cobranca e a confirmacao viviam aqui.
// Sairam junto com o Asaas: sem gateway nao ha conferencia, e confirmacao sem
// conferencia era o bloqueio financeiro que a auditoria apontou. O backend
// responde 503 nas rotas, e a aba mostra o aviso.
// -----------------------------------------------------------------------------

// A conciliacao com o Asaas vivia aqui. Saiu junto com a integracao: sem
// gateway nao ha a quem perguntar se o dinheiro entrou.
//
// Se um gateway voltar, o desenho a recuperar e o de perguntar de dentro para
// fora -- o backend escuta em loopback e webhook nao alcanca este endereco.
// Ver o historico deste arquivo na versao 1.4.2.

async function carregarMapaClientes() {
    if (!mapaInstance || _mapaCarregando) return;
    _mapaCarregando = true;
    var geracao = ++_geracaoMapa;
    try {
        var resp = await fetch('/api/clientes/mapa');
        if (!resp.ok) throw new Error('Falha ao buscar dados do mapa');
        var clientes = await resp.json();
        if (!Array.isArray(clientes) || clientes.length === 0) {
            exibirToast('Nenhum cliente cadastrado no mapa.');
            return;
        }
        mapaMarcadores.forEach(function(m) { mapaInstance.removeLayer(m); });
        mapaMarcadores = [];
        var bounds = [];
        for (var i = 0; i < clientes.length; i++) {
            // Cada cliente custa ate ~1,1 s por causa do limite da Nominatim.
            // Se o mapa foi recarregado nesse meio tempo, este laco esta
            // obsoleto e precisa sair sem tocar no mapa novo.
            if (geracao !== _geracaoMapa) return;
            var c = clientes[i];
            var coords = await geocodificarCliente(c);
            if (geracao !== _geracaoMapa) return;
            if (coords) {
                var badgeClass = c.tipo === 'Retirada' ? 'badge-retirada' : 'badge-entrega';
                // Estilo por classe (ver `.popup-cliente` no CSS). O cinza-ardosia
                // que estava escrito aqui vinha da paleta antiga e ficava
                // ilegivel no tema escuro, porque o popup segue a superficie do
                // app enquanto o texto continuava fixo em cinza claro.
                var popupHtml = '<div class="popup-cliente">' +
                    '<strong class="popup-cliente-nome">' + escaparHtml(c.nome) + '</strong>' +
                    '<span class="' + badgeClass + '">' + escaparHtml(c.tipo) + '</span>' +
                    '<dl class="popup-cliente-dados">' +
                    '<dt>CEP</dt><dd>' + escaparHtml(c.cep) + '</dd>' +
                    (c.rua ? '<dt>Rua</dt><dd>' + escaparHtml(c.rua) + '</dd>' : '') +
                    (c.bairro ? '<dt>Bairro</dt><dd>' + escaparHtml(c.bairro) + '</dd>' : '') +
                    (c.cidade ? '<dt>Cidade</dt><dd>' + escaparHtml(c.cidade) + '</dd>' : '') +
                    '</dl></div>';
                var marker = L.marker([coords.lat, coords.lon], { icon: iconeCliente(c.tipo) })
                    .addTo(mapaInstance).bindPopup(popupHtml);
                mapaMarcadores.push(marker);
                bounds.push([coords.lat, coords.lon]);
            }
        }
        if (bounds.length === 1) {
            // Um ponto so nao tem area: fitBounds vai ao zoom maximo e entrega
            // uma quadra sem contexto. O util e o bairro em volta do cliente.
            mapaInstance.setView(bounds[0], ZOOM_CLIENTE_UNICO);
        } else if (bounds.length > 1) {
            mapaInstance.fitBounds(bounds, { padding: [50, 50], maxZoom: 14 });
        }
    } catch(e) {
        console.error('Erro ao carregar mapa:', e);
        exibirToast('Erro ao carregar mapa.', 'error');
    } finally {
        _mapaCarregando = false;
    }
}


// -----------------------------------------------------------------------------
// Comandos declarativos
//
// Substituem os 36 handlers `onclick=` que viviam no HTML (mais quatro
// montados em template string aqui e um no comercial.js). O motivo nao e
// estilo: enquanto existir um `onclick=` no markup, a Content Security Policy
// precisa liberar `script-src 'unsafe-inline'` -- e essa liberacao vale para
// TODO script inline da pagina, inclusive um que venha a ser injetado por um
// campo de cadastro mal escapado. Sem os handlers, a politica recusa script
// inline por completo.
//
// O atributo e `data-comando`, e nao `data-acao`, porque `data-acao` ja tem
// dono: as notificacoes o usam com os valores "lida", "naolida" e "entrega",
// despachados por um ouvinte proprio na lista. Dois despachantes sobre o mesmo
// atributo disputariam os mesmos elementos.
//
// A LISTA BRANCA e o que torna isto seguro. Um ouvinte delegado que pegasse o
// nome do atributo e o procurasse direto em `window` transformaria qualquer
// HTML injetado numa forma de chamar qualquer funcao do aplicativo. Aqui, o
// nome so vale se estiver declarado abaixo.
//
// A resolucao acontece no clique, e nao no carregamento: parte destas funcoes
// vive no comercial.js, que carrega depois deste arquivo. Um mapa montado
// agora com referencias diretas quebraria com ReferenceError.
//
// `data-arg` vira string; `data-id` vira numero. Dois atributos em vez de
// adivinhar o tipo -- adivinhacao erraria em CEP com zero a esquerda e em nome
// de modal que pareca numero.
// -----------------------------------------------------------------------------
var COMANDOS_PERMITIDOS = [
    'abrirFormularioEntrega',
    'abrirFormularioPedido',
    'abrirFormularioProduto',
    'abrirNotificacoes',
    'adicionarItemAoPedido',
    'alternarSidebar',
    'aplicarFiltros',
    'atualizarNotificacoes',
    'conectarMicrosoft',
    'copiarPixDaLicenca',
    'enviarParaExcel',
    'executarImportacao',
    'fazerBackupSQLite',
    'fecharModal',
    'fecharNotificacoes',
    'gerarPixDaLicenca',
    'limparFiltros',
    'sugerirBairro',
    'toggleFiltro',
    'toggleModoSelecao',
    'toggleTheme',
    'trocarAba'
];

function _despacharComando(evento) {
    var alvo = evento.target.closest('[data-comando]');
    if (!alvo) return;

    var nome = alvo.getAttribute('data-comando');
    if (COMANDOS_PERMITIDOS.indexOf(nome) === -1) {
        console.warn('[comando] fora da lista branca:', nome);
        return;
    }
    var funcao = window[nome];
    if (typeof funcao !== 'function') {
        console.warn('[comando] nao encontrado:', nome);
        return;
    }

    var id = alvo.getAttribute('data-id');
    if (id !== null) { funcao(Number(id)); return; }
    var arg = alvo.getAttribute('data-arg');
    if (arg !== null) { funcao(arg); return; }
    funcao();
}

document.addEventListener('click', _despacharComando);
