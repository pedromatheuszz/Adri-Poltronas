using AdriPoltronas.Application.Abstractions;
using AdriPoltronas.Application.Dtos;

namespace AdriPoltronas.Application.UseCases.Pagamentos;

/// <summary>Lista as cobrancas conforme os filtros da tela.</summary>
public sealed class BuscarPagamentos(IPagamentoRepository pagamentos, IRelogio relogio)
{
    public async Task<IReadOnlyList<PagamentoDto>> ExecutarAsync(
        FiltroDePagamentos filtro, CancellationToken cancelamento = default)
    {
        var encontrados = await pagamentos.BuscarAsync(filtro, cancelamento);
        var agora = relogio.Agora;
        return [.. encontrados.Select(p => PagamentoDto.De(p, agora))];
    }
}

/// <summary>Totais por situacao, exibidos abaixo da lista.</summary>
public sealed class ObterMetricasPagamentos(IPagamentoRepository pagamentos)
{
    public Task<MetricasPagamentosDto> ExecutarAsync(CancellationToken cancelamento = default) =>
        pagamentos.ObterMetricasAsync(cancelamento);
}
