using AdriPoltronas.Application.Abstractions;
using AdriPoltronas.Application.Dtos;

namespace AdriPoltronas.Application.UseCases.Relatorios;

/// <summary>Consulta os clientes que atendem aos filtros e resume os totais.</summary>
public sealed class GerarRelatorio(IDashboardRepository consultas)
{
    public async Task<RelatorioDto> ExecutarAsync(
        FiltroDeRelatorio filtro, CancellationToken cancelamento = default)
    {
        var linhas = await consultas.ClientesDoRelatorioAsync(filtro, cancelamento);
        var entrega = linhas.Count(l => l.Tipo == "Entrega");
        return new RelatorioDto(linhas, linhas.Count, entrega, linhas.Count - entrega);
    }
}

/// <summary>Concentracao de clientes por cidade.</summary>
public sealed class ObterDesempenhoPorRegiao(IDashboardRepository consultas)
{
    public Task<IReadOnlyList<DesempenhoDaRegiao>> ExecutarAsync(
        CancellationToken cancelamento = default) =>
        consultas.DesempenhoPorRegiaoAsync(cancelamento);
}
