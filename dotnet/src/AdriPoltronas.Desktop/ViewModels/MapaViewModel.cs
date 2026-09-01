using System.Collections.ObjectModel;
using AdriPoltronas.Application.Dtos;
using AdriPoltronas.Application.UseCases.Mapa;
using AdriPoltronas.Desktop.Servicos;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using Microsoft.Extensions.Logging;

namespace AdriPoltronas.Desktop.ViewModels;

/// <summary>
/// Aba do mapa: clientes localizados sobre o mapa do OpenStreetMap.
/// </summary>
/// <remarks>
/// A carga e sob demanda, por um botao, e nao ao abrir a aba. Localizar
/// endereco depende de um servico externo com limite de uma consulta por
/// segundo: disparar isso toda vez que alguem passa pela aba gastaria a cota
/// sem ninguem ter pedido o mapa.
/// </remarks>
public sealed partial class MapaViewModel(
    ExecutorDeCasosDeUso casos,
    IFonteDeLadrilhos ladrilhos,
    IDespachante despachante,
    ILogger<MapaViewModel> log) : ViewModelBase, IAtalhosDeTela
{
    public ObservableCollection<PontoNoMapa> Pontos { get; } = [];

    /// <summary>
    /// Fonte das imagens do mapa, repassada ao controle.
    /// </summary>
    /// <remarks>
    /// Exposta pelo ViewModel para que o controle a receba por binding, e nao
    /// resolva um servico por conta propria -- a View continua sem alcancar o
    /// container.
    /// </remarks>
    public IFonteDeLadrilhos Ladrilhos => ladrilhos;

    [ObservableProperty]
    private bool _carregado;

    public bool SemPontos => Carregado && Pontos.Count == 0;

    /// <summary>
    /// Aviso de privacidade, exibido acima do mapa.
    /// </summary>
    /// <remarks>
    /// O endereco do cliente sai da maquina para ser convertido em coordenada.
    /// Isso precisa estar visivel, e nao escondido numa configuracao: quem
    /// opera o sistema e responsavel pelo dado de terceiros que ele manuseia.
    /// </remarks>
    public string AvisoDePrivacidade =>
        "Os enderecos sao enviados ao OpenStreetMap para obter as coordenadas. " +
        "O resultado fica guardado nesta maquina e nao e consultado de novo.";

    IRelayCommand? IAtalhosDeTela.ComandoNovo => null;

    IRelayCommand? IAtalhosDeTela.ComandoAtualizar => CarregarCommand;

    [RelayCommand]
    private Task CarregarAsync() => ExecutarAsync(async () =>
    {
        Mensagem = "Localizando enderecos...";

        var encontrados = await casos.ExecutarAsync<ObterPontosDoMapa, IReadOnlyList<PontoNoMapa>>(
            caso => caso.ExecutarAsync());

        await despachante.NaInterfaceAsync(() =>
        {
            Pontos.Clear();
            foreach (var ponto in encontrados)
            {
                Pontos.Add(ponto);
            }

            Carregado = true;
            OnPropertyChanged(nameof(SemPontos));
        });

        Mensagem = encontrados.Count == 0
            ? "Nenhum endereco pode ser localizado."
            : $"{encontrados.Count} clientes no mapa.";
    }, "Nao foi possivel montar o mapa.");

    protected override void RegistrarFalha(Exception erro, string contexto) =>
        log.LogError(erro, "Falha na tela do mapa: {Contexto}", contexto);
}
