using System.Collections.ObjectModel;
using AdriPoltronas.Application.Dtos;
using AdriPoltronas.Application.UseCases.Notificacoes;
using AdriPoltronas.Desktop.Navigation;
using AdriPoltronas.Desktop.Servicos;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using Microsoft.Extensions.Logging;

namespace AdriPoltronas.Desktop.ViewModels;

/// <summary>
/// Moldura da janela: cabecalho, abas e area de conteudo.
/// </summary>
/// <remarks>
/// As cinco abas, o sino de notificacoes e o botao de tema sao os mesmos da
/// interface web. Quem usa o sistema todo dia nao deveria precisar reaprender
/// onde as coisas ficam so porque a tecnologia mudou.
/// </remarks>
public sealed partial class MainWindowViewModel : ViewModelBase
{
    private readonly INavegacao _navegacao;
    private readonly ExecutorDeCasosDeUso _casos;
    private readonly ITema _tema;
    private readonly IDespachante _despachante;
    private readonly ILogger<MainWindowViewModel> _log;

    public MainWindowViewModel(
        INavegacao navegacao,
        ExecutorDeCasosDeUso casos,
        ITema tema,
        IDespachante despachante,
        ILogger<MainWindowViewModel> log)
    {
        _navegacao = navegacao;
        _casos = casos;
        _tema = tema;
        _despachante = despachante;
        _log = log;
        _navegacao.Mudou += destino => Conteudo = destino;
    }

    /// <summary>ViewModel da tela exibida. O ViewLocator escolhe a View.</summary>
    [ObservableProperty]
    private ViewModelBase? _conteudo;

    [ObservableProperty]
    private string _secaoAtual = "Dashboard";

    [ObservableProperty]
    private bool _temaEscuro = true;

    [ObservableProperty]
    private bool _painelDeNotificacoesAberto;

    [ObservableProperty]
    private int _naoLidas;

    /// <summary>Alertas do sino, ja ordenados por urgencia.</summary>
    public ObservableCollection<NotificacaoDto> Notificacoes { get; } = [];

    public bool TemNotificacoes => Notificacoes.Count > 0;

    public bool TemNaoLidas => NaoLidas > 0;

    public string CaminhoDoBanco => Program.CaminhoDoBanco();

    public override void AoEntrar()
    {
        _tema.Restaurar();
        TemaEscuro = _tema.EstaEscuro;
        AbrirDashboard();
        _ = AtualizarNotificacoesAsync();
    }

    [RelayCommand]
    private void AbrirDashboard() => Ir<DashboardViewModel>("Dashboard");

    [RelayCommand]
    private void AbrirClientes() => Ir<ClientesViewModel>("Clientes");

    [RelayCommand]
    private void AbrirMapa() => Ir<MapaViewModel>("Mapa");

    [RelayCommand]
    private void AbrirPagamentos() => Ir<PagamentosViewModel>("Pagamentos");

    [RelayCommand]
    private void AbrirRelatorios() => Ir<RelatoriosViewModel>("Relatorios");

    [RelayCommand]
    private void AlternarTema()
    {
        _tema.Alternar();
        TemaEscuro = _tema.EstaEscuro;
    }

    [RelayCommand]
    private void AlternarPainelDeNotificacoes() =>
        PainelDeNotificacoesAberto = !PainelDeNotificacoesAberto;

    [RelayCommand]
    private void FecharPainelDeNotificacoes() => PainelDeNotificacoesAberto = false;

    [RelayCommand]
    private Task AtualizarNotificacoesAsync() => ExecutarAsync(
        CarregarNotificacoesAsync, "Nao foi possivel carregar as notificacoes.");

    /// <summary>
    /// Recarrega os alertas. NAO passa por <see cref="ViewModelBase.ExecutarAsync"/>.
    /// </summary>
    /// <remarks>
    /// Quem chama de dentro de um comando ja esta sob a guarda de reentrancia.
    /// Envolver de novo faria a guarda ver <c>Ocupado</c> e sair calada -- as
    /// notificacoes seriam marcadas como lidas no banco e o contador do sino
    /// continuaria mostrando o numero antigo.
    /// </remarks>
    private async Task CarregarNotificacoesAsync()
    {
        var painel = await _casos.ExecutarAsync<ObterNotificacoes, PainelDeNotificacoes>(
            caso => caso.ExecutarAsync());

        await _despachante.NaInterfaceAsync(() =>
        {
            Notificacoes.Clear();
            foreach (var alerta in painel.Itens)
            {
                Notificacoes.Add(alerta);
            }

            NaoLidas = painel.NaoLidas;
            OnPropertyChanged(nameof(TemNotificacoes));
        });
    }

    [RelayCommand]
    private Task MarcarNotificacoesLidasAsync() => ExecutarAsync(async () =>
    {
        var chaves = Notificacoes.Where(n => !n.Lida).Select(n => n.Chave).ToList();
        if (chaves.Count == 0)
        {
            return;
        }

        await _casos.ExecutarAsync<MarcarNotificacoesLidas, bool>(async caso =>
        {
            await caso.ExecutarAsync(chaves);
            return true;
        });

        // Recarrega em vez de mexer na lista na mao: o estado exibido passa a
        // ser o que o banco tem, e nao um palpite da tela.
        await CarregarNotificacoesAsync();
    }, "Nao foi possivel marcar as notificacoes.");

    /// <summary>Ctrl+N: delega para a tela aberta, se ela cadastrar algo.</summary>
    [RelayCommand]
    private void AtalhoNovo() => (Conteudo as IAtalhosDeTela)?.ComandoNovo?.Execute(null);

    /// <summary>Ctrl+R: recarrega a tela aberta e tambem o sino.</summary>
    [RelayCommand]
    private void AtalhoAtualizar()
    {
        (Conteudo as IAtalhosDeTela)?.ComandoAtualizar?.Execute(null);
        AtualizarNotificacoesCommand.Execute(null);
    }

    partial void OnNaoLidasChanged(int value) => OnPropertyChanged(nameof(TemNaoLidas));

    private void Ir<TViewModel>(string secao) where TViewModel : ViewModelBase
    {
        SecaoAtual = secao;
        PainelDeNotificacoesAberto = false;
        _navegacao.IrPara<TViewModel>();
    }

    protected override void RegistrarFalha(Exception erro, string contexto) =>
        _log.LogError(erro, "Falha na janela principal: {Contexto}", contexto);
}
