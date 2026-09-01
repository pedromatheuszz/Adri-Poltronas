using AdriPoltronas.Application.Abstractions;
using AdriPoltronas.Domain.Entities;
using Microsoft.EntityFrameworkCore;

namespace AdriPoltronas.Infrastructure.Persistence.Repositories;

/// <inheritdoc cref="IHistoricoRepository"/>
public sealed class HistoricoRepository(AdriPoltronasDbContext contexto) : IHistoricoRepository
{
    public void Adicionar(RegistroHistorico registro) => contexto.Historico.Add(registro);

    public async Task<IReadOnlyList<RegistroHistorico>> UltimosAsync(
        int quantidade, CancellationToken cancelamento = default) =>
        await contexto.Historico
            .OrderByDescending(r => r.DataHora)
            .ThenByDescending(r => r.Id)
            .Take(quantidade)
            .AsNoTracking()
            .ToListAsync(cancelamento);
}
