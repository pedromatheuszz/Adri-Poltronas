using Avalonia.Threading;

namespace AdriPoltronas.Desktop.Servicos;

/// <inheritdoc cref="IDespachante"/>
public sealed class DespachanteDoAvalonia : IDespachante
{
    public Task NaInterfaceAsync(Action acao) =>
        // Avalonia so aceita mudanca em colecao ligada a tela vinda deste
        // thread; a busca roda em Task.Run e chegaria de outro.
        Dispatcher.UIThread.InvokeAsync(acao).GetTask();
}
