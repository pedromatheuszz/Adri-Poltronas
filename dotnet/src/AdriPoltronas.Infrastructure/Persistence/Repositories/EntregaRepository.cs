using AdriPoltronas.Application.Abstractions;
using AdriPoltronas.Domain.Entities;
using AdriPoltronas.Domain.Enums;
using Microsoft.EntityFrameworkCore;

namespace AdriPoltronas.Infrastructure.Persistence.Repositories;

/// <inheritdoc cref="IEntregaRepository"/>
public sealed class EntregaRepository(AdriPoltronasDbContext contexto) : IEntregaRepository
{
    public async Task<IReadOnlyList<EntregaAgendada>> BuscarAsync(
        string? status, CancellationToken cancelamento = default)
    {
        var consulta = contexto.Entregas.AsQueryable();

        if (StatusEntregaExtensions.TentarConverter(status, out var situacao))
        {
            consulta = consulta.Where(e => e.Status == situacao);
        }

        var encontradas = await consulta.AsNoTracking().ToListAsync(cancelamento);

        // A ordenacao e por data de entrega, que no banco e texto AAAA-MM-DD --
        // ordenavel como texto, mas nao alcancavel pelo LINQ atraves do
        // conversor. Ordenar aqui custa nada no volume de uma agenda.
        return [.. encontradas.OrderBy(e => e.DataEntrega.Texto).ThenBy(e => e.HoraEntrega)];
    }

    public Task<EntregaAgendada?> ObterPorIdAsync(
        int id, CancellationToken cancelamento = default) =>
        contexto.Entregas.FirstOrDefaultAsync(e => e.Id == id, cancelamento);

    public async Task<IReadOnlyList<EntregaAgendada>> PendentesAteAsync(
        DateTime limite, CancellationToken cancelamento = default)
    {
        var pendentes = await contexto.Entregas
            .Where(e => e.Status == StatusEntrega.Pendente)
            .AsNoTracking()
            .ToListAsync(cancelamento);

        // Inclui as atrasadas: sao as que mais precisam aparecer no alerta.
        return [.. pendentes
            .Where(e => e.DataEntrega.DiasAte(limite) is <= 0)
            .OrderBy(e => e.DataEntrega.Texto)];
    }

    public void Adicionar(EntregaAgendada entrega) => contexto.Entregas.Add(entrega);

    public void Remover(EntregaAgendada entrega) => contexto.Entregas.Remove(entrega);
}
