const API_URL = '/api/clientes';
let modoSelecaoAtivo = false;
let saindoSelecao = false;
let intervaloChecagem = null;
let debounceTimer;
var filtrosAtivos = { tipos: ['Entrega', 'Retirada'], cidades: [] };

function escaparHtml(str) {
    if (!str) return '';
    return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}

function exibirToast(mensagem, tipo) {
    tipo = tipo || 'success';
    var toast = document.getElementById('toast');
    if (toast) {
        toast.innerText = mensagem;
        toast.style.backgroundColor = tipo === 'success' ? '#27ae60' : '#e74c3c';
        toast.className = 'show';
        setTimeout(function(){ toast.className = toast.className.replace('show',''); }, 3000);
    }
}

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

    caixa.setAttribute('data-variante', opcoes.variante || 'perigo');
    elIcone.innerHTML = ICONES_CONFIRMACAO[opcoes.icone] || ICONES_CONFIRMACAO.alerta;
    elTitulo.textContent = opcoes.titulo || 'Confirmar';
    elMsg.textContent = opcoes.mensagem || '';
    btnOk.textContent = opcoes.textoConfirmar || 'Confirmar';
    btnCancelar.textContent = opcoes.textoCancelar || 'Cancelar';

    return new Promise(function(resolver) {
        var finalizado = false;

        function encerrar(resultado) {
            if (finalizado) return;
            finalizado = true;
            overlay.classList.remove('ativo');
            btnOk.removeEventListener('click', aoConfirmar);
            btnCancelar.removeEventListener('click', aoCancelar);
            overlay.removeEventListener('click', aoClicarFora);
            document.removeEventListener('keydown', aoTeclar);
            resolver(resultado);
        }

        function aoConfirmar() { encerrar(true); }
        function aoCancelar() { encerrar(false); }
        function aoClicarFora(e) { if (e.target === overlay) encerrar(false); }
        function aoTeclar(e) {
            if (e.key === 'Escape') encerrar(false);
            else if (e.key === 'Enter' && document.activeElement !== btnCancelar) {
                e.preventDefault(); encerrar(true);
            }
        }

        btnOk.addEventListener('click', aoConfirmar);
        btnCancelar.addEventListener('click', aoCancelar);
        overlay.addEventListener('click', aoClicarFora);
        document.addEventListener('keydown', aoTeclar);

        overlay.classList.add('ativo');
        // Foco no cancelar: acao destrutiva nao deve ser confirmada por engano
        // quem chegou ali pelo teclado.
        setTimeout(function(){ btnCancelar.focus(); }, 60);
    });
}

function aplicarMascaraCep(e) {
    var value = e.target.value.replace(/\D/g, '');
    if (value.length > 5) value = value.replace(/^(\d{5})(\d)/, '$1-$2');
    e.target.value = value;
}

function trocarAba(aba) {
    // Hide all tabs (remove active class; CSS handles display:none via .tab-content)
    document.querySelectorAll('.tab-content').forEach(function(s) {
        s.classList.remove('active');
        s.style.display = '';
    });
    document.querySelectorAll('.nav-tab').forEach(function(t){ t.classList.remove('active'); });
    var section = document.getElementById('aba-' + aba);
    var tab = document.querySelector('#navTabs [onclick*="' + aba + '"]');
    if (section) {
        // Force display:block first (opacity still 0 from CSS), then trigger opacity transition
        section.style.display = 'block';
        section.offsetHeight; // force reflow so transition fires
        section.classList.add('active');
    }
    if (tab) tab.classList.add('active');
    if (aba === 'dashboard') { carregarDashboardGraficos(); }
    if (aba === 'mapa') { setTimeout(function() { initMapa(); carregarMapaClientes(); }, 100); }
    if (aba === 'relatorios') { carregarRelatorio(); }
    if (aba === 'pagamentos') { carregarPagamentos(); }
}

var chartInstances = {};

document.addEventListener('DOMContentLoaded', function() {
    carregarClientes();
    checarLoginExistente();
    carregarNotificacoes();
    initTheme();
    registrarAtalhosTeclado();

    initObservacoesCounter();
    carregarDashboardGraficos();

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
            if (e.target === overlay) overlay.classList.remove('ativo');
        });
    });

    document.addEventListener('click', function(e) {
        var dropdown = document.getElementById('filtroDropdown');
        var btnFiltro = document.getElementById('btnFiltro');
        if (!dropdown) return;
        if (!btnFiltro.contains(e.target) && !dropdown.contains(e.target)) {
            dropdown.classList.remove('ativo');
            btnFiltro.classList.remove('ativo');
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

    var modalNomeCancelar = document.getElementById('modalNomeCancelar');
    var modalNomeConfirmar = document.getElementById('modalNomeConfirmar');
    if (modalNomeCancelar) modalNomeCancelar.addEventListener('click', function(){ document.getElementById('modalNomeArquivo').classList.remove('ativo'); });
    if (modalNomeConfirmar) modalNomeConfirmar.addEventListener('click', function() {
        document.getElementById('modalNomeArquivo').classList.remove('ativo');
        if (window._confirmNomeCallback) window._confirmNomeCallback();
    });

    var modalImportarCancelar = document.getElementById('modalImportarCancelar');
    if (modalImportarCancelar) modalImportarCancelar.addEventListener('click', function(){ document.getElementById('modalImportar').classList.remove('ativo'); });

    // Formulario de novo recebimento
    var formNovoRecebimento = document.getElementById('formNovoRecebimento');
    if (formNovoRecebimento) {
        formNovoRecebimento.addEventListener('submit', salvarNovoRecebimento);
    }

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
            var modalAtivo = document.querySelector('.modal-overlay.ativo');
            if (!modalAtivo) {
                var inputId = document.getElementById('clienteId');
                if (inputId && inputId.value) { cancelarEdicao(); exibirToast('Edicao cancelada.'); }
            } else { modalAtivo.classList.remove('ativo'); }
        }
    });
});

async function carregarDashboardGraficos() {
    try {
        var resp = await fetch('/api/dashboard/dados?t=' + Date.now());
        if (!resp.ok) return;
        var dados = await resp.json();
        if (dados.erro) return;

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
        if (el30) el30.textContent = cadastros30d + '%';

        renderizarFinanceiro(dados.financeiro);

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
                            backgroundColor: tipoLabels.map(function(l) { return l === 'Retirada' ? '#f59e0b' : '#10b981'; }),
                            borderColor: tipoLabels.map(function(l) { return l === 'Retirada' ? 'rgba(245,158,11,0.8)' : 'rgba(16,185,129,0.8)'; }),
                            borderWidth: 2
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: {
                            legend: { position: 'bottom', labels: { color: '#94a3b8', padding: 16, font: { size: 13 } } }
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
                            backgroundColor: 'rgba(59,130,246,0.6)',
                            borderColor: 'rgba(59,130,246,1)',
                            borderWidth: 1,
                            borderRadius: 6
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: { legend: { display: false } },
                        scales: {
                            x: { ticks: { color: '#94a3b8', font: { size: 11 } }, grid: { display: false } },
                            y: { ticks: { color: '#94a3b8', stepSize: 1 }, grid: { color: 'rgba(255,255,255,0.05)' } }
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
                            borderColor: '#8b5cf6',
                            backgroundColor: 'rgba(139,92,246,0.1)',
                            fill: true,
                            tension: 0.4,
                            pointRadius: 3,
                            pointBackgroundColor: '#8b5cf6'
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: { legend: { display: false } },
                        scales: {
                            x: { ticks: { color: '#94a3b8', maxTicksLimit: 10, font: { size: 11 } }, grid: { display: false } },
                            y: { ticks: { color: '#94a3b8', stepSize: 1 }, grid: { color: 'rgba(255,255,255,0.05)' }, beginAtZero: true }
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
                return '<div style="display:flex;justify-content:space-between;align-items:center;padding:0.6rem 0;border-bottom:1px solid var(--glass-border);">' +
                    '<span style="font-weight:600;">' + escaparHtml(c.nome) + '</span>' +
                    '<span style="font-size:0.8rem;color:var(--text-muted);">' + escaparHtml(c.cidade || '-') + ' &middot; <span class="' + badgeClass + '" style="font-size:0.7rem;">' + escaparHtml(c.tipo) + '</span></span>' +
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

function renderizarFinanceiro(fin) {
    if (!fin) return;

    var def = function(id, texto) { var el = document.getElementById(id); if (el) el.textContent = texto; };
    def('metricFaturamentoMes', formatarReal(fin.faturamento_mes));
    def('metricAReceber', formatarReal(fin.a_receber));
    def('metricEmAtraso', formatarReal(fin.em_atraso));
    def('metricTicketMedio', formatarReal(fin.ticket_medio_mes));
    def('metricQtdRecebimentos', fin.qtd_recebimentos_mes + ' recebimento(s) no mes');
    def('metricQtdAtraso', fin.qtd_em_atraso > 0 ? fin.qtd_em_atraso + ' cobranca(s) vencida(s)' : 'Nenhuma cobranca vencida');
    def('metricMesAnterior', 'Mes anterior: ' + formatarReal(fin.faturamento_mes_anterior));

    // Variacao vs mes anterior. `null` = nao havia base de comparacao, entao
    // nao inventa um "0%" que sugeriria estabilidade.
    var elVar = document.getElementById('metricVariacao');
    if (elVar) {
        if (fin.variacao_percentual === null || fin.variacao_percentual === undefined) {
            elVar.textContent = '';
            elVar.className = 'metrica-variacao';
        } else {
            var v = fin.variacao_percentual;
            var subiu = v >= 0;
            elVar.textContent = (subiu ? '▲ +' : '▼ ') + v.toFixed(1).replace('.', ',') + '%';
            elVar.className = 'metrica-variacao ' + (subiu ? 'variacao-alta' : 'variacao-baixa');
        }
    }

    var ctx = document.getElementById('chartReceitaMensal');
    var serie = fin.serie_mensal || [];
    if (!ctx || typeof Chart === 'undefined' || serie.length === 0) return;

    // Destaca o mes corrente (ultimo da serie) para a leitura de "onde estou".
    var ultimoIndice = serie.length - 1;
    var cores = serie.map(function(_, i) { return i === ultimoIndice ? '#10b981' : 'rgba(59,130,246,0.65)'; });

    if (chartInstances.receita) chartInstances.receita.destroy();
    chartInstances.receita = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: serie.map(function(p){ return rotuloMes(p.mes); }),
            datasets: [{
                label: 'Receita',
                data: serie.map(function(p){ return p.total; }),
                backgroundColor: cores,
                borderRadius: 6,
                maxBarThickness: 64
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: function(item) { return formatarReal(item.parsed.y); }
                    }
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: {
                        color: corDoTexto(),
                        callback: function(v) { return 'R$ ' + v.toLocaleString('pt-BR'); }
                    },
                    grid: { color: corDaGrade() }
                },
                x: { ticks: { color: corDoTexto() }, grid: { display: false } }
            }
        }
    });
}

function corDoTexto() {
    return getComputedStyle(document.documentElement).getPropertyValue('--text-muted').trim() || '#94a3b8';
}

function corDaGrade() {
    return document.documentElement.getAttribute('data-theme') === 'light'
        ? 'rgba(0,0,0,0.07)' : 'rgba(255,255,255,0.07)';
}



function initTheme() {
    var saved = localStorage.getItem('adri-theme') || 'dark';
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
    if (sun && moon) {
        sun.style.display = theme === 'dark' ? 'block' : 'none';
        moon.style.display = theme === 'light' ? 'block' : 'none';
    }
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
    badge.style.display = naoLidas > 0 ? 'flex' : 'none';
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
    if (btnTodas) btnTodas.style.display = naoLidas > 0 ? 'block' : 'none';

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
    if (!panel) return;
    renderizarNotificacoes();
    panel.classList.toggle('ativo');
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
}

async function carregarClientes() {
    var busca = (document.getElementById('inputPesquisa') || {}).value || '';
    busca = busca.trim();
    try {
        var response = await fetch(API_URL+'?busca='+encodeURIComponent(busca));
        if (!response.ok) throw new Error('Falha');
        var clientes = await response.json();
        // Cache para uso offline
        if (typeof OfflineManager !== 'undefined' && clientes.length > 0) {
            OfflineManager.cacheClientes(clientes);
        }
        clientes = clientes.filter(clientePassaFiltro);
        renderizarTabela(clientes);
    } catch (error) {
        console.error('Erro ao carregar do servidor:', error);
        // Fallback para cache apenas quando offline
        if (!navigator.onLine) {
            carregarClientesOffline();
        } else {
            exibirToast('Erro ao carregar clientes.', 'error');
        }
    }
}

async function carregarClientesOffline(mostrarToast) {
    try {
        if (typeof OfflineManager === 'undefined') return;
        var clientes = await OfflineManager.getCachedClientes();
        if (!clientes || clientes.length === 0) return;
        clientes = clientes.filter(clientePassaFiltro);
        renderizarTabela(clientes);
        if (mostrarToast) {
            exibirToast('Exibindo dados do cache offline.', 'success');
        }
    } catch (error) {
        console.error('Erro ao carregar cache offline:', error);
    }
}

async function registrarNovoCliente(dados) {
    // Se offline, salvar na fila de sincronizacao
    if (!navigator.onLine) {
        try {
            await OfflineManager.savePendingAction('create', dados);
            exibirToast('Salvo offline! Sera sincronizado quando voltar online.', 'success');
            cancelarEdicao();
            // Adicionar ao cache local com ID temporario negativo
            var cached = await OfflineManager.getCachedClientes();
            var novoId = -Date.now(); // ID temporario negativo para evitar conflito
            dados.id = novoId;
            dados.criado_em = new Date().toISOString();
            dados._offline = true; // Flag para identificar offline
            cached.push(dados);
            await OfflineManager.cacheClientes(cached);
            carregarClientesOffline(true);
        } catch (erro) { exibirToast('Erro ao salvar offline.', 'error'); }
        return;
    }
    try {
        var resposta = await fetch(API_URL, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(dados) });
        var resultado = await resposta.json();
        if (!resposta.ok) throw new Error(resultado.erro || 'Erro');
        exibirToast('Cliente cadastrado!');
        cancelarEdicao(); carregarClientes(); carregarDashboardGraficos();
    } catch (erro) { exibirToast('Erro ao registrar.', 'error'); }
}

async function atualizarClienteServidor(id, dados) {
    // Se offline, salvar na fila de sincronizacao
    if (!navigator.onLine) {
        try {
            dados.id = id;
            await OfflineManager.savePendingAction('update', dados);
            exibirToast('Atualizacao salva offline! Sera sincronizado quando voltar online.', 'success');
            cancelarEdicao();
            // Atualizar cache local
            var cached = await OfflineManager.getCachedClientes();
            var idx = cached.findIndex(function(c) { return c.id === id; });
            if (idx !== -1) { cached[idx] = Object.assign(cached[idx], dados); }
            await OfflineManager.cacheClientes(cached);
            carregarClientesOffline(true);
        } catch (erro) { exibirToast('Erro ao salvar offline.', 'error'); }
        return;
    }
    try {
        var resposta = await fetch(API_URL+'/'+id, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(dados) });
        if (!resposta.ok) throw new Error('Erro');
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

    // Se offline, salvar na fila de sincronizacao
    if (!navigator.onLine) {
        try {
            // Se ID é temporario (negativo), não precisa enviar ao servidor
            if (id < 0) {
                exibirToast('Cliente removido do cache offline.', 'success');
            } else {
                await OfflineManager.savePendingAction('delete', { id: id });
                exibirToast('Exclusao salva offline! Sera sincronizado quando voltar online.', 'success');
            }
            cancelarEdicao();
            // Remover do cache local
            var cached = await OfflineManager.getCachedClientes();
            cached = cached.filter(function(c) { return c.id !== id; });
            await OfflineManager.cacheClientes(cached);
            carregarClientesOffline(true);
        } catch (erro) { exibirToast('Erro ao salvar exclusao offline.', 'error'); }
        return;
    }
    try {
        var resposta = await fetch(API_URL+'/'+id, { method: 'DELETE' });
        var dados = await resposta.json();
        if (!resposta.ok) throw new Error(dados.erro || 'Erro');
        exibirToast('Cliente excluido!');
        cancelarEdicao(); carregarClientes(); carregarDashboardGraficos();
    } catch (erro) { exibirToast('Erro: ' + erro.message, 'error'); }
}

function renderizarTabela(clientes) {
    var tabela = document.getElementById('tabelaClientes');
    if (!tabela) return;
    tabela.innerHTML = '';
    if (!Array.isArray(clientes)) clientes = [];
    if (clientes.length === 0) {
        tabela.innerHTML = '<tr><td colspan="6" style="text-align:center;padding:3rem;color:var(--text-muted);"><p>Nenhum cliente encontrado.</p></td></tr>';
        return;
    }
    clientes.forEach(function(c) {
        var tr = document.createElement('tr');
        var badgeClass = (c.entrega_retirada || 'Entrega') === 'Retirada' ? 'badge-retirada' : 'badge-entrega';
        var idSeguro = escaparHtml('' + c.id);
        tr.innerHTML =
            '<td class="col-checkbox"><input type="checkbox" class="client-checkbox" value="'+idSeguro+'"></td>' +
            '<td class="col-nome"><strong>'+escaparHtml(c.nome)+'</strong></td>' +
            '<td class="col-cidade">'+escaparHtml(c.cidade||'')+'</td>' +
            '<td class="col-bairro">'+escaparHtml(c.bairro||'')+'</td>' +
            '<td class="col-tipo"><span class="'+badgeClass+'">'+escaparHtml(c.entrega_retirada||'Entrega')+'</span></td>' +
            '<td class="col-acoes" style="text-align:right;"><div style="display:inline-flex;gap:0.5rem;">' +
            '<button class="btn" style="background:#475569;padding:0.3rem 0.6rem;font-size:0.85rem;" data-action="editar" data-id="'+idSeguro+'" data-nome="'+escaparHtml(c.nome||'')+'" data-cep="'+escaparHtml(c.cep||'')+'" data-rua="'+escaparHtml(c.rua||'')+'" data-bairro="'+escaparHtml(c.bairro||'')+'" data-cidade="'+escaparHtml(c.cidade||'')+'" data-tipo="'+escaparHtml(c.entrega_retirada||'Entrega')+'" data-obs="'+escaparHtml(c.observacoes||'')+'">Editar</button>' +
            '<button class="btn" style="background:#ef4444;padding:0.3rem 0.6rem;font-size:0.85rem;" data-action="excluir" data-id="'+idSeguro+'">Excluir</button>' +
            '</div></td>';
        tabela.appendChild(tr);
    });
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
        if (txt) txt.innerText = 'Sair da Selecao';
        document.body.classList.add('modo-selecao-ativo');
    } else {
        if (btn) btn.classList.remove('ativo');
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
    if (dropdown.classList.contains('ativo')) { dropdown.classList.remove('ativo'); if(btnFiltro) btnFiltro.classList.remove('ativo'); }
    else { carregarCidadesParaFiltro(); dropdown.classList.add('ativo'); if(btnFiltro) btnFiltro.classList.add('ativo'); }
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

function aplicarFiltros() {
    filtrosAtivos.tipos = Array.from(document.querySelectorAll('input[name="filtroTipo"]:checked')).map(function(cb){ return cb.value; });
    filtrosAtivos.cidades = Array.from(document.querySelectorAll('input[name="filtroCidade"]:checked')).map(function(cb){ return cb.value; });
    var dd = document.getElementById('filtroDropdown'); if(dd) dd.classList.remove('ativo');
    var bf = document.getElementById('btnFiltro'); if(bf) bf.classList.remove('ativo');
    carregarClientes();
}

function limparFiltros() {
    filtrosAtivos = { tipos: ['Entrega', 'Retirada'], cidades: [] };
    document.querySelectorAll('input[name="filtroTipo"]').forEach(function(cb){ cb.checked = true; });
    document.querySelectorAll('input[name="filtroCidade"]').forEach(function(cb){ cb.checked = true; });
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

function fazerBackupJSON() {
    window.open('/api/backup/json', '_blank');
    exibirToast('Backup JSON iniciado!');
}

function fazerBackupSQLite() {
    window.open('/api/backup/sqlite', '_blank');
    exibirToast('Backup do banco iniciado!');
}

function abrirModalImportar() {
    var modal = document.getElementById('modalImportar');
    if (modal) {
        modal.classList.add('ativo');
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
        if (resultado) { resultado.style.display = 'block'; resultado.style.background = 'rgba(16,185,129,0.1)'; resultado.style.border = '1px solid rgba(16,185,129,0.3)'; resultado.innerHTML = '<strong>Importacao concluida!</strong><br>Importados: '+dados.sucessos+'<br>Duplicados: '+dados.duplicados+'<br>Erros: '+dados.erros; }
        exibirToast(dados.sucessos + ' clientes importados!');
        carregarClientes();
        carregarDashboardGraficos();
    } catch(e) {
        if (resultado) { resultado.style.display = 'block'; resultado.style.background = 'rgba(239,68,68,0.1)'; resultado.style.border = '1px solid rgba(239,68,68,0.3)'; resultado.innerHTML = '<strong>Erro:</strong> '+e.message; }
        exibirToast('Erro na importacao.', 'error');
    }
}

async function checarLoginExistente() {
    try {
        var resp = await fetch('/api/auth/status');
        var status = await resp.json();
        if (status.logado) { atualizarVisualBotaoConexao(status.conta); if(intervaloChecagem){ clearInterval(intervaloChecagem); intervaloChecagem = null; } return true; }
        else { resetarVisualBotaoConexao(); }
    } catch(_) {}
    return false;
}

function atualizarVisualBotaoConexao(conta) {
    var btnConectar = document.getElementById('btnConectarMicrosoft');
    var btnEnviar = document.getElementById('btnEnviarExcel');
    var txtConectar = document.getElementById('txtBtnConectar');
    if (btnConectar) { btnConectar.classList.add('conectado'); btnConectar.classList.remove('carregando'); }
    if (txtConectar) txtConectar.innerText = 'Conectado (' + conta.split('@')[0] + ')';
    if (btnEnviar) btnEnviar.disabled = false;
}

function resetarVisualBotaoConexao() {
    var btnConectar = document.getElementById('btnConectarMicrosoft');
    var btnEnviar = document.getElementById('btnEnviarExcel');
    var txtConectar = document.getElementById('txtBtnConectar');
    if (btnConectar) btnConectar.classList.remove('conectado');
    if (txtConectar) txtConectar.innerText = 'Conectar Microsoft';
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
        if (resp.ok) { resetarVisualBotaoConexao(); exibirToast('Desconectado da Microsoft.'); }
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
    document.getElementById('modalNomeArquivo').classList.add('ativo');
}

async function enviarExcelComNome(ids, nomeArquivo) {
    var btnEnviar = document.getElementById('btnEnviarExcel');
    try {
        if (btnEnviar) { btnEnviar.disabled = true; btnEnviar.classList.add('carregando'); }
        var resp = await fetch('/api/excel/enviar', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ids: ids, nome_arquivo: nomeArquivo }) });
        var dados = await resp.json();
        if (!resp.ok) throw new Error(dados.erro || 'Falha');
        exibirToast('Planilha enviada!');
    } catch(e) { exibirToast('Erro: ' + e.message, 'error'); }
    finally { if (btnEnviar) { btnEnviar.disabled = false; btnEnviar.classList.remove('carregando'); } }
}

// -----------------------------------------------------------------------------
// Relatorios
// -----------------------------------------------------------------------------
function obterParamsRelatorio() {
    var tipo = (document.getElementById('relFiltroTipo') || {}).value || '';
    var cidade = (document.getElementById('relFiltroCidade') || {}).value || '';
    var dataInicio = (document.getElementById('relDataInicio') || {}).value || '';
    var dataFim = (document.getElementById('relDataFim') || {}).value || '';
    var params = new URLSearchParams();
    if (tipo) params.set('tipo', tipo);
    if (cidade) params.set('cidade', cidade);
    if (dataInicio) params.set('data_inicio', dataInicio);
    if (dataFim) params.set('data_fim', dataFim);
    return params;
}

async function carregarRelatorio() {
    var contador = document.getElementById('relatorioContador');
    var previewCard = document.getElementById('relatorioPreviewCard');
    var tabela = document.getElementById('relatorioTabela');
    var dataInicio = (document.getElementById('relDataInicio') || {}).value || '';
    var dataFim = (document.getElementById('relDataFim') || {}).value || '';
    if (dataInicio && dataFim && dataFim < dataInicio) {
        exibirToast('Data final deve ser posterior a data inicial.', 'error');
        return;
    }
    try {
        if (contador) contador.textContent = 'Carregando...';
        var params = obterParamsRelatorio();
        var resp = await fetch('/api/relatorios?' + params.toString());
        if (!resp.ok) throw new Error('Falha ao buscar dados');
        var dados = await resp.json();
        var clientes = dados.clientes || [];
        if (contador) contador.textContent = clientes.length + ' cliente(s) encontrado(s).';
        if (clientes.length === 0) {
            if (previewCard) previewCard.style.display = 'none';
            return;
        }
        if (previewCard) previewCard.style.display = 'block';
        if (tabela) {
            tabela.innerHTML = clientes.map(function(c) {
                var badgeClass = c.entrega_retirada === 'Retirada' ? 'badge-retirada' : 'badge-entrega';
                var dataFormatada = c.criado_em ? new Date(c.criado_em).toLocaleDateString('pt-BR') : '-';
                return '<tr>' +
                    '<td><strong>' + escaparHtml(c.nome) + '</strong></td>' +
                    '<td>' + escaparHtml(c.cidade || '-') + '</td>' +
                    '<td>' + escaparHtml(c.bairro || '-') + '</td>' +
                    '<td><span class="' + badgeClass + '" style="font-size:0.75rem;">' + escaparHtml(c.entrega_retirada) + '</span></td>' +
                    '<td>' + escaparHtml(c.cep || '-') + '</td>' +
                    '<td style="font-size:0.8rem;color:var(--text-muted);">' + dataFormatada + '</td>' +
                    '</tr>';
            }).join('');
        }
        carregarRelatorioRegioes(dados.regioes || []);
    } catch(e) {
        console.error('Erro ao carregar relatorio:', e);
        exibirToast('Erro ao carregar relatorio.', 'error');
        if (contador) contador.textContent = 'Erro ao carregar dados.';
    }
}

function exportarRelatorio() {
    var params = obterParamsRelatorio();
    var formato = (document.getElementById('relFormato') || {}).value || 'csv';
    params.set('formato', formato);
    window.open('/api/relatorios/exportar?' + params.toString(), '_blank');
    exibirToast('Relatorio exportado!');
}

function carregarRelatorioRegioes(regioes) {
    var container = document.getElementById('relatorioRegioes');
    if (!container) return;
    if (!regioes || regioes.length === 0) {
        container.innerHTML = '<div style="padding:1rem;text-align:center;color:var(--text-muted);">Nenhum dado por regiao.</div>';
        return;
    }
    var total = regioes.reduce(function(a, r) { return a + r.total; }, 0);
    container.innerHTML = '<table style="width:100%;"><thead><tr><th style="text-align:left;">Cidade</th><th style="text-align:center;">Total</th><th style="text-align:center;">Entregas</th><th style="text-align:center;">Retiradas</th><th style="text-align:right;">%</th></tr></thead><tbody>' +
        regioes.map(function(r) {
            var pct = total > 0 ? Math.round((r.total / total) * 100) : 0;
            return '<tr><td><strong>' + escaparHtml(r.cidade) + '</strong></td>' +
                '<td style="text-align:center;">' + r.total + '</td>' +
                '<td style="text-align:center;"><span class="badge-entrega" style="font-size:0.75rem;">' + r.entregas + '</span></td>' +
                '<td style="text-align:center;"><span class="badge-retirada" style="font-size:0.75rem;">' + r.retiradas + '</span></td>' +
                '<td style="text-align:right;color:var(--text-muted);">' + pct + '%</td></tr>';
        }).join('') +
        '</tbody></table>';
}

// -----------------------------------------------------------------------------
// Mapa de Clientes (Leaflet/OpenStreetMap)
// -----------------------------------------------------------------------------
var mapaInstance = null;
var mapaMarcadores = [];
var _geocacheCoords = {};
var _mapaCarregando = false;

function initMapa() {
    var mapContainer = document.getElementById('mapaClientes');
    if (!mapContainer || mapaInstance) return;
    mapaInstance = L.map('mapaClientes', {
        center: [-15.7801, -47.9292],
        zoom: 4,
        zoomControl: true
    });
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; OpenStreetMap contributors',
        maxZoom: 18
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
        if (coords) { _geocacheCoords[cacheKey] = coords; return coords; }
    }

    // Passo 2: Fallback - apenas cidade + UF
    if (cliente.cidade && cliente.cidade.trim()) {
        await new Promise(function(r) { setTimeout(r, 1100); });
        var queryCidade = cliente.cidade.trim() + (uf ? ', ' + uf : '') + ', Brasil';
        var coords = await geocodificarCidade(queryCidade);
        if (coords) { _geocacheCoords[cacheKey] = coords; return coords; }
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
// Pagamentos
// -----------------------------------------------------------------------------

async function carregarPagamentos() {
    carregarPagamentosLista();
    carregarPagamentosMetricas();
    // Load clients into the modal's select (recClienteId)
    try {
        var resp = await fetch('/api/clientes?busca=');
        var clientes = await resp.json();
        var select = document.getElementById('recClienteId');
        if (select) {
            var valAtual = select.value;
            select.innerHTML = '<option value="">Selecione um cliente...</option>';
            clientes.forEach(function(c) {
                var opt = document.createElement('option');
                opt.value = c.id;
                opt.textContent = c.nome + (c.cidade ? ' (' + c.cidade + ')' : '');
                opt.setAttribute('data-nome', c.nome);
                select.appendChild(opt);
            });
            if (valAtual) select.value = valAtual;
        }
    } catch(_) {}
}

async function carregarPagamentosMetricas() {
    try {
        var resp = await fetch('/api/pagamentos/metricas');
        var dados = await resp.json();
        var elRecebido = document.getElementById('pagTotalRecebido');
        var elPendente = document.getElementById('pagTotalPendente');
        var elAtrasado = document.getElementById('pagTotalAtrasado');
        if (elRecebido) elRecebido.textContent = 'R$ ' + (dados.total_recebido || 0).toFixed(2).replace('.', ',');
        if (elPendente) elPendente.textContent = 'R$ ' + (dados.total_pendente || 0).toFixed(2).replace('.', ',');
        if (elAtrasado) elAtrasado.textContent = 'R$ ' + (dados.total_atrasado || 0).toFixed(2).replace('.', ',');
    } catch(_) {}
}

// carregarClientesParaPagamento removed — clients are now loaded directly
// in carregarPagamentos() and abrirModalNovoRecebimento() targeting recClienteId

async function carregarPagamentosLista() {
    try {
        var filtroCliente = (document.getElementById('pagFiltroCliente') || {}).value || '';
        var filtroStatus = (document.getElementById('pagFiltroStatus') || {}).value || '';
        var resp = await fetch('/api/pagamentos');
        var pagamentos = await resp.json();
        // Apply client-side filters
        if (filtroCliente) {
            var term = filtroCliente.toLowerCase();
            pagamentos = pagamentos.filter(function(p) {
                return (p.cliente_nome || '').toLowerCase().indexOf(term) !== -1;
            });
        }
        if (filtroStatus) {
            pagamentos = pagamentos.filter(function(p) {
                return p.status === filtroStatus;
            });
        }
        renderizarTabelaPagamentos(pagamentos);
    } catch(e) {
        console.error('Erro ao carregar pagamentos:', e);
    }
}

function renderizarTabelaPagamentos(pagamentos) {
    var tbody = document.getElementById('tabelaPagamentos');
    if (!tbody) return;
    if (!pagamentos || pagamentos.length === 0) {
        tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;padding:2rem;color:var(--text-muted);"><p>Nenhum pagamento registrado.</p></td></tr>';
        return;
    }
    tbody.innerHTML = pagamentos.map(function(p) {
        var statusClass = 'badge-pendente';
        if (p.status === 'Recebido') statusClass = 'badge-recebido';
        else if (p.status === 'Atrasado') statusClass = 'badge-atrasado';
        else if (p.status === 'Cancelado') statusClass = 'badge-cancelado';
        var tipoClass = 'badge-entrega';
        if (p.tipo_pagamento === 'Boleto') tipoClass = 'badge-retirada';
        else if (p.tipo_pagamento === 'Dinheiro') tipoClass = 'badge-recebido';
        else if (p.tipo_pagamento === 'Cartao') tipoClass = 'badge-pendente';
        else if (p.tipo_pagamento === 'Outro') tipoClass = 'badge-atrasado';
        var valor = parseFloat(p.valor || 0).toFixed(2).replace('.', ',');
        var dataVen = p.data_vencimento ? p.data_vencimento.split('-').reverse().join('/') : '-';
        var acoes = '';
        if (p.status === 'Pendente') {
            if (!p.asaas_payment_id) {
                acoes = '<button class="btn" style="background:#3b82f6;padding:0.3rem 0.6rem;font-size:0.8rem;" onclick="gerarCobranca(' + p.id + ')">Gerar Cobranca</button>';
            } else {
                acoes = '<button class="btn" style="background:#10b981;padding:0.3rem 0.6rem;font-size:0.8rem;" onclick="confirmarPagamentoLocal(' + p.id + ')">Confirmar</button>';
            }
            acoes += ' <button class="btn" style="background:#ef4444;padding:0.3rem 0.6rem;font-size:0.8rem;" onclick="cancelarPagamentoLocal(' + p.id + ')">Cancelar</button>';
        }
        return '<tr>' +
            '<td><strong>' + escaparHtml(p.cliente_nome || '') + '</strong></td>' +
            '<td>R$ ' + valor + '</td>' +
            '<td>' + escaparHtml(p.descricao || '-') + '</td>' +
            '<td><span class="' + statusClass + '" style="font-size:0.75rem;">' + escaparHtml(p.status) + '</span></td>' +
            '<td><span class="' + tipoClass + '" style="font-size:0.75rem;">' + escaparHtml(p.tipo_pagamento || 'Pix') + '</span></td>' +
            '<td style="font-size:0.8rem;color:var(--text-muted);">' + dataVen + '</td>' +
            '<td style="text-align:right;">' + acoes + '</td>' +
            '</tr>';
    }).join('');
}

// salvarPagamento() and cancelarPagamentoForm() removed — replaced by
// salvarNovoRecebimento() and fecharModalNovoRecebimento() which target
// the new modal IDs (recClienteId, recValor, recDataPagamento, etc.)

async function gerarCobranca(pagamentoId) {
    exibirToast('Gerando cobranca...');
    try {
        var resp = await fetch('/api/pagamentos/gerar-cobranca', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ pagamento_id: pagamentoId })
        });
        var dados = await resp.json();
        if (!resp.ok) throw new Error(dados.erro || 'Erro');
        exibirToast(dados.mensagem || 'Cobranca gerada!');
        exibirDadosCobranca(pagamentoId);
        carregarPagamentos();
    } catch(e) { exibirToast('Erro: ' + e.message, 'error'); }
}

async function exibirDadosCobranca(pagamentoId) {
    try {
        var resp = await fetch('/api/pagamentos/' + pagamentoId + '/cobranca-dados');
        var dados = await resp.json();
        if (!resp.ok) return;
        var modal = document.getElementById('modalCobranca');
        var conteudo = document.getElementById('cobrancaConteudo');
        if (!modal || !conteudo) return;
        if (dados.tipo_pagamento === 'Pix') {
            var qrImg = dados.pix_qr_code ? '<img src="data:image/png;base64,' + dados.pix_qr_code + '" style="max-width:280px;margin:1rem auto;display:block;border-radius:12px;border:2px solid var(--glass-border);">' : '<p style="color:var(--text-muted);">QR Code nao disponivel</p>';
            var payload = dados.pix_payload || '';
            conteudo.innerHTML = '<div style="text-align:center;">' +
                '<h3 style="margin-bottom:0.5rem;color:var(--primary);">Pagamento Pix</h3>' +
                '<p style="color:var(--text-muted);margin-bottom:1rem;">Valor: R$ ' + (dados.valor || 0).toFixed(2).replace('.', ',') + '</p>' +
                qrImg +
                (payload ? '<div style="margin-top:1rem;background:var(--input-bg);border-radius:10px;padding:0.8rem;font-size:0.75rem;word-break:break-all;color:var(--text-main);border:1px solid var(--glass-border);">' + escaparHtml(payload) + '</div>' : '') +
                (payload ? '<button class="btn btn-primary" style="margin-top:0.75rem;" onclick="copiarPix()">Copiar Copia e Cola</button>' : '') +
                '</div>';
        } else if (dados.tipo_pagamento === 'Boleto') {
            var url = dados.boleto_url || '';
            conteudo.innerHTML = '<div style="text-align:center;">' +
                '<h3 style="margin-bottom:0.5rem;color:var(--primary);">Boleto Bancario</h3>' +
                '<p style="color:var(--text-muted);margin-bottom:1rem;">Valor: R$ ' + (dados.valor || 0).toFixed(2).replace('.', ',') + '</p>' +
                (dados.nosso_numero ? '<p style="color:var(--text-muted);font-size:0.85rem;">Nosso Numero: ' + escaparHtml(dados.nosso_numero) + '</p>' : '') +
                (url ? '<a href="' + escaparHtml(url) + '" target="_blank" class="btn btn-primary" style="margin-top:1rem;">Abrir Boleto</a>' : '<p style="color:var(--text-muted);">URL do boleto nao disponivel.</p>') +
                '</div>';
        }
        modal.classList.add('ativo');
    } catch(e) { console.error('Erro ao obter dados da cobranca:', e); }
}

function fecharModalCobranca() {
    var modal = document.getElementById('modalCobranca');
    if (modal) modal.classList.remove('ativo');
}

async function copiarPix() {
    var payloadEl = document.querySelector('#cobrancaConteudo div[style*="word-break"]');
    if (payloadEl && navigator.clipboard) {
        try {
            await navigator.clipboard.writeText(payloadEl.textContent);
            exibirToast('Copia e Cola copiado!');
        } catch(_) { exibirToast('Falha ao copiar.', 'error'); }
    }
}

async function confirmarPagamentoLocal(pagamentoId) {
    try {
        var resp = await fetch('/api/pagamentos/' + pagamentoId + '/confirmar', { method: 'POST' });
        if (resp.ok) {
            exibirToast('Pagamento confirmado!');
            carregarPagamentos();
        } else { exibirToast('Erro ao confirmar.', 'error'); }
    } catch(_) { exibirToast('Erro ao confirmar pagamento.', 'error'); }
}

async function cancelarPagamentoLocal(pagamentoId) {
    var confirmado = await confirmarAcao({
        titulo: 'Cancelar Cobranca',
        mensagem: 'Esta cobranca sera cancelada e nao podera ser recuperada. Deseja continuar?',
        textoConfirmar: 'Cancelar cobranca',
        textoCancelar: 'Voltar',
        icone: 'alerta',
        variante: 'perigo'
    });
    if (!confirmado) return;
    try {
        var resp = await fetch('/api/pagamentos/' + pagamentoId, { method: 'DELETE' });
        var dados = await resp.json();
        if (!resp.ok) throw new Error(dados.erro || 'Erro');
        exibirToast('Pagamento cancelado!');
        carregarPagamentos();
    } catch(e) { exibirToast('Erro: ' + e.message, 'error'); }
}

// -----------------------------------------------------------------------------
// Novo Recebimento Manual
// -----------------------------------------------------------------------------
async function abrirModalNovoRecebimento() {
    var modal = document.getElementById('modalNovoRecebimento');
    if (!modal) return;
    
    // Carregar lista de clientes no select
    var select = document.getElementById('recClienteId');
    if (select) {
        try {
            var resp = await fetch('/api/clientes?busca=');
            var clientes = await resp.json();
            select.innerHTML = '<option value="">Selecione um cliente...</option>';
            clientes.forEach(function(c) {
                var opt = document.createElement('option');
                opt.value = c.id;
                opt.textContent = c.nome + (c.cidade ? ' (' + c.cidade + ')' : '');
                opt.setAttribute('data-nome', c.nome);
                select.appendChild(opt);
            });
        } catch(_) {}
    }
    
    // Definir data atual como padrao
    var dataInput = document.getElementById('recDataPagamento');
    if (dataInput) {
        var hoje = new Date().toISOString().split('T')[0];
        dataInput.value = hoje;
    }
    
    // Limpar formulario
    var form = document.getElementById('formNovoRecebimento');
    if (form) form.reset();
    if (dataInput) dataInput.value = hoje;
    
    modal.classList.add('ativo');
}

function fecharModalNovoRecebimento() {
    var modal = document.getElementById('modalNovoRecebimento');
    if (modal) modal.classList.remove('ativo');
}

async function salvarNovoRecebimento(e) {
    if (e) e.preventDefault();
    
    var clienteSelect = document.getElementById('recClienteId');
    var clienteId = clienteSelect ? clienteSelect.value : '';
    if (!clienteId) {
        exibirToast('Selecione um cliente.', 'error');
        return;
    }
    
    var clienteOpt = clienteSelect.options[clienteSelect.selectedIndex];
    var clienteNome = clienteOpt ? (clienteOpt.getAttribute('data-nome') || clienteOpt.textContent) : '';
    
    var valor = parseFloat((document.getElementById('recValor') || {}).value || 0);
    if (isNaN(valor) || valor <= 0) {
        exibirToast('Informe um valor valido.', 'error');
        return;
    }
    
    var dataPagamento = (document.getElementById('recDataPagamento') || {}).value || '';
    if (!dataPagamento) {
        exibirToast('Informe a data do recebimento.', 'error');
        return;
    }
    
    var tipoPagamento = (document.getElementById('recTipoPagamento') || {}).value || 'Pix';
    var status = (document.getElementById('recStatus') || {}).value || 'Recebido';
    var descricao = (document.getElementById('recDescricao') || {}).value || '';
    
    var dados = {
        cliente_id: parseInt(clienteId),
        cliente_nome: clienteNome,
        valor: valor,
        descricao: descricao,
        data_vencimento: dataPagamento,
        tipo_pagamento: tipoPagamento,
        status: status,
        data_pagamento: status === 'Recebido' ? dataPagamento : ''
    };
    
    try {
        var resp = await fetch('/api/pagamentos', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(dados)
        });
        var resultado = await resp.json();
        if (!resp.ok) throw new Error(resultado.erro || 'Erro ao registrar recebimento');
        
        exibirToast('Recebimento registrado com sucesso!');
        fecharModalNovoRecebimento();
        carregarPagamentos();
    } catch(e) {
        exibirToast('Erro: ' + e.message, 'error');
    }
}

async function carregarMapaClientes() {
    if (!mapaInstance || _mapaCarregando) return;
    _mapaCarregando = true;
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
            var c = clientes[i];
            var coords = await geocodificarCliente(c);
            if (coords) {
                var badgeClass = c.tipo === 'Retirada' ? 'badge-retirada' : 'badge-entrega';
                var popupHtml = '<div style="min-width:200px;font-family:Inter,sans-serif;">' +
                    '<strong style="font-size:1.05em;">' + escaparHtml(c.nome) + '</strong><br>' +
                    '<span class="' + badgeClass + '" style="font-size:0.7rem;margin:4px 0;display:inline-block;">' + escaparHtml(c.tipo) + '</span>' +
                    '<hr style="margin:6px 0;border-color:#e5e7eb;">' +
                    '<div style="font-size:0.85em;color:#475569;line-height:1.6;">' +
                    '<div><strong>CEP:</strong> ' + escaparHtml(c.cep) + '</div>' +
                    (c.rua ? '<div><strong>Rua:</strong> ' + escaparHtml(c.rua) + '</div>' : '') +
                    (c.bairro ? '<div><strong>Bairro:</strong> ' + escaparHtml(c.bairro) + '</div>' : '') +
                    (c.cidade ? '<div><strong>Cidade:</strong> ' + escaparHtml(c.cidade) + '</div>' : '') +
                    '</div></div>';
                var marker = L.marker([coords.lat, coords.lon]).addTo(mapaInstance).bindPopup(popupHtml);
                mapaMarcadores.push(marker);
                bounds.push([coords.lat, coords.lon]);
            }
        }
        if (bounds.length > 0) {
            mapaInstance.fitBounds(bounds, { padding: [50, 50], maxZoom: 14 });
        }
    } catch(e) {
        console.error('Erro ao carregar mapa:', e);
        exibirToast('Erro ao carregar mapa.', 'error');
    } finally {
        _mapaCarregando = false;
    }
}


