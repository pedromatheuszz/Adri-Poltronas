using AdriPoltronas.Domain.Entities;

namespace AdriPoltronas.Application.Abstractions;

/// <summary>Acesso as entregas agendadas.</summary>
public interface IEntregaRepository
{
    Task<IReadOnlyList<EntregaAgendada>> BuscarAsync(
        string? status, CancellationToken cancelamento = default);

    Task<EntregaAgendada?> ObterPorIdAsync(int id, CancellationToken cancelamento = default);

    /// <summary>Entregas pendentes marcadas ate o limite informado, e as atrasadas.</summary>
    Task<IReadOnlyList<EntregaAgendada>> PendentesAteAsync(
        DateTime limite, CancellationToken cancelamento = default);

    void Adicionar(EntregaAgendada entrega);

    void Remover(EntregaAgendada entrega);
}
