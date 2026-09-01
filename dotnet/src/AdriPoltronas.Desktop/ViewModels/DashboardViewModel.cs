using System.Collections.ObjectModel;
using AdriPoltronas.Application.Dtos;
using AdriPoltronas.Application.UseCases.Dashboard;
using AdriPoltronas.Desktop.Servicos;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using Microsoft.Extensions.Logging;

namespace AdriPoltronas.Desktop.ViewModels;

/// <summary>
/// Painel inicial: cartoes de cadastro, cartoes financeiros e quatro graficos.
/// </summary>
/// <remarks>
/// Tudo vem de uma unica chamada ao caso de uso. A tela nunca aparece com
/// metade dos cartoes preenchidos, que era o comportamento da versao web --
/// cinco requisicoes independentes, cada uma pintando um pedaco quando
/// chegava.
/// </remarks>
public sealed partial class DashboardViewModel(
    ExecutorDeCasosDeUso casos,
    IDespachante despachante,
    ILogger<DashboardViewModel> log) : ViewModelBase, IAtalhosDeTela
{
    [ObservableProperty]
    private MetricasDashboardDto _cadastro = MetricasDashboardDto.Vazio;

    [ObservableProperty]
    private MetricasFinanceirasDto _financeiro = MetricasFinanceirasDto.Vazio;

    [ObservableProperty]
    private IReadOnlyList<PontoDoGrafico> _receitaMensal = [];

    [ObservableProperty]
    private IReadOnlyList<PontoDoGrafico> _entregaVersusRetirada = [];

    [ObservableProperty]
    private IReadOnlyList<PontoDoGrafico> _clientesPorCidade = [];

    [ObservableProperty]
    private IReadOnlyList<PontoDoGrafico> _cadastrosPorMes = [];

    public ObservableCollection<ClienteDto> UltimosClientes { get; } = [];

    /// <summary>Rotulo da janela de cadastros recentes, no plural certo.</summary>
    public string RotuloDeRecentes => $"Novos ({ObterPainel.DiasDaJanela} dias)";

    /// <summary>Seta e sinal da variacao mensal, prontos para exibir.</summary>
    public string VariacaoFormatada => Financeiro.VariacaoPercentual switch
    {
        > 0 => $"▲ {Financeiro.VariacaoPercentual:0.#}% vs mes anterior",
        < 0 => $"▼ {Financeiro.VariacaoPercentual:0.#}% vs mes anterior",
        _ => "sem variacao vs mes anterior",
    };

    public bool VariacaoPositiva => Financeiro.VariacaoPercentual >= 0;

    IRelayCommand? IAtalhosDeTela.ComandoNovo => null;

    IRelayCommand? IAtalhosDeTela.ComandoAtualizar => RecarregarCommand;

    public override void AoEntrar() => RecarregarCommand.Execute(null);

    [RelayCommand]
    private Task RecarregarAsync() => ExecutarAsync(async () =>
    {
        var painel = await casos.ExecutarAsync<ObterPainel, PainelDto>(
            caso => caso.ExecutarAsync());

        await despachante.NaInterfaceAsync(() =>
        {
            Cadastro = painel.Cadastro;
            Financeiro = painel.Financeiro;
            ReceitaMensal = painel.Graficos.ReceitaMensal;
            EntregaVersusRetirada = painel.Graficos.EntregaVersusRetirada;
            ClientesPorCidade = painel.Graficos.ClientesPorCidade;
            CadastrosPorMes = painel.Graficos.CadastrosPorMes;

            UltimosClientes.Clear();
            foreach (var cliente in painel.UltimosClientes)
            {
                UltimosClientes.Add(cliente);
            }
        });

        Mensagem = string.Empty;
    }, "Nao foi possivel carregar o painel.");

    partial void OnFinanceiroChanged(MetricasFinanceirasDto value)
    {
        OnPropertyChanged(nameof(VariacaoFormatada));
        OnPropertyChanged(nameof(VariacaoPositiva));
    }

    protected override void RegistrarFalha(Exception erro, string contexto) =>
        log.LogError(erro, "Falha no painel: {Contexto}", contexto);
}
