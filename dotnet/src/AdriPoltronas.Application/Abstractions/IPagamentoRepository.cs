using AdriPoltronas.Application.Dtos;
using AdriPoltronas.Domain.Entities;

namespace AdriPoltronas.Application.Abstractions;

/// <summary>Acesso as cobrancas.</summary>
public interface IPagamentoRepository
{
    Task<IReadOnlyList<Pagamento>> BuscarAsync(
        FiltroDePagamentos filtro, CancellationToken cancelamento = default);

    Task<Pagamento?> ObterPorIdAsync(int id, CancellationToken cancelamento = default);

    /// <summary>Cobrancas pendentes que vencem ate o limite informado.</summary>
    /// <remarks>Base dos alertas de vencimento; nao traz recebidas nem canceladas.</remarks>
    Task<IReadOnlyList<Pagamento>> AVencerAteAsync(
        DateTime limite, CancellationToken cancelamento = default);

    void Adicionar(Pagamento pagamento);

    void Remover(Pagamento pagamento);

    /// <summary>Totais por situacao, somados no banco.</summary>
    Task<MetricasPagamentosDto> ObterMetricasAsync(CancellationToken cancelamento = default);
}
