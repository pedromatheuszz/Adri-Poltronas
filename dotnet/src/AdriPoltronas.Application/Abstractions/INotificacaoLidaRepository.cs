namespace AdriPoltronas.Application.Abstractions;

/// <summary>
/// Estado de leitura das notificacoes.
/// </summary>
/// <remarks>
/// Guarda apenas chaves. As notificacoes em si sao recalculadas a cada
/// consulta, entao nao ha o que persistir alem do que o operador ja dispensou.
/// </remarks>
public interface INotificacaoLidaRepository
{
    Task<IReadOnlySet<string>> ChavesLidasAsync(CancellationToken cancelamento = default);

    /// <summary>Marca as chaves como lidas. Repetir uma chave ja marcada nao e erro.</summary>
    Task MarcarComoLidasAsync(
        IReadOnlyCollection<string> chaves, CancellationToken cancelamento = default);

    Task LimparAsync(CancellationToken cancelamento = default);
}
