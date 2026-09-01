using AdriPoltronas.Application.Abstractions;
using AdriPoltronas.Infrastructure.Persistence.Entities;
using Microsoft.EntityFrameworkCore;

namespace AdriPoltronas.Infrastructure.Persistence.Repositories;

/// <inheritdoc cref="INotificacaoLidaRepository"/>
public sealed class NotificacaoLidaRepository(
    AdriPoltronasDbContext contexto, IRelogio relogio) : INotificacaoLidaRepository
{
    public async Task<IReadOnlySet<string>> ChavesLidasAsync(
        CancellationToken cancelamento = default)
    {
        var chaves = await contexto.NotificacoesLidas
            .Select(l => l.Chave)
            .AsNoTracking()
            .ToListAsync(cancelamento);

        return chaves.ToHashSet(StringComparer.Ordinal);
    }

    public async Task MarcarComoLidasAsync(
        IReadOnlyCollection<string> chaves, CancellationToken cancelamento = default)
    {
        if (chaves.Count == 0)
        {
            return;
        }

        // Marcar duas vezes a mesma notificacao e normal -- o operador clica em
        // "marcar todas" com itens ja lidos na lista. Filtrar antes evita a
        // violacao de chave primaria, sem precisar de tratamento de excecao.
        var existentes = await ChavesLidasAsync(cancelamento);
        var novas = chaves
            .Where(chave => !string.IsNullOrWhiteSpace(chave) && !existentes.Contains(chave))
            .Distinct(StringComparer.Ordinal)
            .Select(chave => new NotificacaoLida { Chave = chave, LidaEm = relogio.Agora });

        contexto.NotificacoesLidas.AddRange(novas);
        await contexto.SaveChangesAsync(cancelamento);
    }

    public async Task LimparAsync(CancellationToken cancelamento = default)
    {
        contexto.NotificacoesLidas.RemoveRange(contexto.NotificacoesLidas);
        await contexto.SaveChangesAsync(cancelamento);
    }
}
