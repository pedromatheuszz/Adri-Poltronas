using System.Collections.ObjectModel;
using AdriPoltronas.Application.Common;
using AdriPoltronas.Application.Dtos;
using AdriPoltronas.Application.UseCases.Relatorios;
using AdriPoltronas.Desktop.Navigation;
using AdriPoltronas.Desktop.Servicos;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using Microsoft.Extensions.Logging;

namespace AdriPoltronas.Desktop.ViewModels;

/// <summary>Aba de relatorios: filtros, previa, desempenho por regiao e exportacao.</summary>
public sealed partial class RelatoriosViewModel(
    ExecutorDeCasosDeUso casos,
    IDialogos dialogos,
    IDespachante despachante,
    ILogger<RelatoriosViewModel> log) : ViewModelBase, IAtalhosDeTela
{
    public IReadOnlyList<string> TiposDisponiveis { get; } = ["Todos", "Entrega", "Retirada"];

    public IReadOnlyList<string> FormatosDisponiveis { get; } = ["CSV", "XLSX"];

    public ObservableCollection<LinhaDoRelatorio> Linhas { get; } = [];

    public ObservableCollection<DesempenhoDaRegiao> Regioes { get; } = [];

    [ObservableProperty]
    private string _tipo = "Todos";

    [ObservableProperty]
    private string _cidade = string.Empty;

    [ObservableProperty]
    private string _dataInicio = string.Empty;

    [ObservableProperty]
    private string _dataFim = string.Empty;

    [ObservableProperty]
    private string _formato = "CSV";

    [ObservableProperty]
    private RelatorioDto _resumo = RelatorioDto.Vazio;

    public bool SemResultado => Linhas.Count == 0;

    IRelayCommand? IAtalhosDeTela.ComandoNovo => null;

    IRelayCommand? IAtalhosDeTela.ComandoAtualizar => VisualizarCommand;

    public override void AoEntrar() => VisualizarCommand.Execute(null);

    [RelayCommand]
    private Task VisualizarAsync() => ExecutarAsync(async () =>
    {
        var relatorio = await casos.ExecutarAsync<GerarRelatorio, RelatorioDto>(
            caso => caso.ExecutarAsync(Filtro()));
        var regioes = await casos.ExecutarAsync<
            ObterDesempenhoPorRegiao, IReadOnlyList<DesempenhoDaRegiao>>(
            caso => caso.ExecutarAsync());

        await despachante.NaInterfaceAsync(() =>
        {
            Linhas.Clear();
            foreach (var linha in relatorio.Linhas)
            {
                Linhas.Add(linha);
            }

            Regioes.Clear();
            foreach (var regiao in regioes)
            {
                Regioes.Add(regiao);
            }

            Resumo = relatorio;
            OnPropertyChanged(nameof(SemResultado));
        });

        Mensagem = $"{relatorio.Total} clientes no filtro atual.";
    }, "Nao foi possivel gerar o relatorio.");

    [RelayCommand]
    private Task ExportarAsync() => ExecutarAsync(async () =>
    {
        var formato = Formato == "XLSX" ? FormatoDeArquivo.Xlsx : FormatoDeArquivo.Csv;
        var caminho = await dialogos.EscolherArquivoParaSalvarAsync(
            "Exportar relatorio", $"relatorio-clientes.{Formato.ToLowerInvariant()}", formato);

        if (string.IsNullOrWhiteSpace(caminho))
        {
            return;
        }

        var resultado = await casos.ExecutarAsync<ExportarRelatorio, Resultado>(
            caso => caso.ExecutarAsync(Filtro(), caminho, formato));

        Mensagem = resultado.Sucesso ? $"Relatorio gravado em {caminho}." : resultado.Mensagem;
    }, "Nao foi possivel exportar o relatorio.");

    private FiltroDeRelatorio Filtro() => new(
        Tipo == "Todos" ? null : Tipo,
        Cidade,
        DataInicio,
        DataFim);

    protected override void RegistrarFalha(Exception erro, string contexto) =>
        log.LogError(erro, "Falha na tela de relatorios: {Contexto}", contexto);
}
