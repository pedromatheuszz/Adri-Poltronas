using AdriPoltronas.Application.Abstractions;
using AdriPoltronas.Application.Dtos;

namespace AdriPoltronas.Application.UseCases.Dashboard;

/// <summary>Contagens do painel inicial.</summary>
public sealed class ObterMetricasDashboard(IClienteRepository clientes, IRelogio relogio)
{
    /// <summary>Janela de "cadastros recentes" exibida no painel.</summary>
    public const int DiasDaJanela = 30;

    public Task<MetricasDashboardDto> ExecutarAsync(CancellationToken cancelamento = default)
    {
        // O corte de data e decidido aqui, e nao no SQL do repositorio: assim a
        // regra fica visivel e testavel sem banco.
        var inicio = relogio.Agora.AddDays(-DiasDaJanela);
        return clientes.ObterMetricasAsync(inicio, cancelamento);
    }
}
