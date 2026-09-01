using AdriPoltronas.Application.Abstractions;
using AdriPoltronas.Application.Dtos;

namespace AdriPoltronas.Application.UseCases.Entregas;

/// <summary>Lista as entregas agendadas, opcionalmente por situacao.</summary>
public sealed class BuscarEntregas(IEntregaRepository entregas, IRelogio relogio)
{
    public async Task<IReadOnlyList<EntregaDto>> ExecutarAsync(
        string? status = null, CancellationToken cancelamento = default)
    {
        var encontradas = await entregas.BuscarAsync(status, cancelamento);
        var agora = relogio.Agora;
        return [.. encontradas.Select(e => EntregaDto.De(e, agora))];
    }
}
