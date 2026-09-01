using AdriPoltronas.Application.Abstractions;

namespace AdriPoltronas.Infrastructure.Persistence;

/// <inheritdoc cref="IUnidadeDeTrabalho"/>
/// <remarks>
/// O <c>SaveChangesAsync</c> do EF Core ja abre uma transacao propria quando
/// nao ha uma em curso, entao tudo que os repositorios marcaram entra junto ou
/// nao entra. Nao ha transacao explicita aqui porque ela seria redundante.
/// </remarks>
public sealed class UnidadeDeTrabalho(AdriPoltronasDbContext contexto) : IUnidadeDeTrabalho
{
    public Task<int> ConfirmarAsync(CancellationToken cancelamento = default) =>
        contexto.SaveChangesAsync(cancelamento);
}
