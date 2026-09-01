using AdriPoltronas.Application.Dtos;
using AdriPoltronas.Desktop.Views;
using Avalonia.Controls;
using Avalonia.Controls.ApplicationLifetimes;
using Avalonia.Platform.Storage;
using Avalonia.Threading;

namespace AdriPoltronas.Desktop.Navigation;

/// <inheritdoc cref="IDialogos"/>
/// <remarks>
/// A implementacao conhece <c>Window</c>; os ViewModels, nao. E aqui que a
/// dependencia da interface grafica termina.
/// </remarks>
public sealed class Dialogos : IDialogos
{
    public Task<DadosDoCliente?> EditarClienteAsync(ClienteDto? existente) =>
        AbrirAsync(dono => new ClienteDialog(existente).ShowDialog<DadosDoCliente?>(dono));

    public Task<DadosDoPagamento?> NovoPagamentoAsync(IReadOnlyList<ClienteDto> clientes) =>
        AbrirAsync(dono => new PagamentoDialog(clientes).ShowDialog<DadosDoPagamento?>(dono));

    public async Task MostrarCobrancaAsync(PagamentoDto pagamento) =>
        await AbrirAsync<object?>(async dono =>
        {
            await new CobrancaDialog(pagamento).ShowDialog(dono);
            return null;
        });

    public async Task<bool> ConfirmarAsync(string titulo, string pergunta) =>
        await AbrirAsync(dono =>
            new ConfirmacaoDialog(titulo, pergunta).ShowDialog<bool>(dono));

    public Task<string?> EscolherArquivoParaSalvarAsync(
        string titulo, string nomeSugerido, FormatoDeArquivo formato) =>
        AbrirAsync(async dono =>
        {
            var escolhido = await dono.StorageProvider.SaveFilePickerAsync(
                new FilePickerSaveOptions
                {
                    Title = titulo,
                    SuggestedFileName = nomeSugerido,
                    DefaultExtension = Extensao(formato),
                    FileTypeChoices = [Tipo(formato)],
                });

            return escolhido?.TryGetLocalPath();
        });

    public Task<string?> EscolherArquivoParaAbrirAsync(string titulo) =>
        AbrirAsync(async dono =>
        {
            var escolhidos = await dono.StorageProvider.OpenFilePickerAsync(
                new FilePickerOpenOptions
                {
                    Title = titulo,
                    AllowMultiple = false,
                    FileTypeFilter =
                    [
                        new FilePickerFileType("Planilhas e dados")
                        {
                            Patterns = ["*.csv", "*.xlsx", "*.json"],
                        },
                    ],
                });

            return escolhidos.Count == 0 ? null : escolhidos[0].TryGetLocalPath();
        });

    /// <summary>
    /// Abre no thread da interface, com a janela principal como dona.
    /// </summary>
    /// <remarks>
    /// Comandos podem terminar fora do thread da interface (a busca roda em
    /// <c>Task.Run</c>); abrir janela de la lancaria excecao. Sem janela
    /// principal -- so acontece em teste -- devolve o valor neutro em vez de
    /// estourar.
    /// </remarks>
    private static async Task<T?> AbrirAsync<T>(Func<Window, Task<T?>> abrir)
    {
        return await Dispatcher.UIThread.InvokeAsync(() =>
        {
            var dono = JanelaPrincipal();
            return dono is null ? Task.FromResult<T?>(default) : abrir(dono);
        });
    }

    private static string Extensao(FormatoDeArquivo formato) => formato switch
    {
        FormatoDeArquivo.Xlsx => "xlsx",
        FormatoDeArquivo.Json => "json",
        _ => "csv",
    };

    private static FilePickerFileType Tipo(FormatoDeArquivo formato) => formato switch
    {
        FormatoDeArquivo.Xlsx => new FilePickerFileType("Planilha do Excel")
        {
            Patterns = ["*.xlsx"],
        },
        FormatoDeArquivo.Json => new FilePickerFileType("Arquivo JSON")
        {
            Patterns = ["*.json"],
        },
        _ => new FilePickerFileType("Texto separado por ponto e virgula")
        {
            Patterns = ["*.csv"],
        },
    };

    private static Window? JanelaPrincipal() =>
        Avalonia.Application.Current?.ApplicationLifetime
            is IClassicDesktopStyleApplicationLifetime desktop
            ? desktop.MainWindow
            : null;
}
