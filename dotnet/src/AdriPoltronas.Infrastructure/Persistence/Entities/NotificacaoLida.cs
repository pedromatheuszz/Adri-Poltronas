namespace AdriPoltronas.Infrastructure.Persistence.Entities;

/// <summary>
/// Chave de uma notificacao que o operador ja dispensou.
/// </summary>
/// <remarks>
/// Vive na Infrastructure, e nao no Domain, porque nao e conceito de negocio:
/// e o unico pedaco de notificacao que precisa sobreviver ao fechamento do
/// aplicativo. A notificacao em si e recalculada a cada consulta.
/// </remarks>
public sealed class NotificacaoLida
{
    public required string Chave { get; init; }

    public DateTime LidaEm { get; init; }
}
