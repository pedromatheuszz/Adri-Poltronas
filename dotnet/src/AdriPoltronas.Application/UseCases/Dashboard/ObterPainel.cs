using AdriPoltronas.Application.Abstractions;
using AdriPoltronas.Application.Dtos;

namespace AdriPoltronas.Application.UseCases.Dashboard;

/// <summary>
/// Monta a tela inicial inteira.
/// </summary>
/// <remarks>
/// A interface antiga disparava cinco requisicoes para desenhar o painel e
/// cada cartao aparecia quando chegava. Aqui e uma unidade: ou o painel esta
/// pronto, ou continua no estado anterior -- nao existe meio-termo em que o
/// faturamento ja apareceu mas o grafico ainda nao.
/// </remarks>
public sealed class ObterPainel(
    IClienteRepository clientes,
    IDashboardRepository painel,
    IRelogio relogio)
{
    /// <summary>Janela de cadastros recentes exibida no cartao.</summary>
    public const int DiasDaJanela = 30;

    /// <summary>Meses das series historicas.</summary>
    public const int MesesDaSerie = 6;

    /// <summary>Cidades exibidas no grafico de concentracao.</summary>
    public const int CidadesNoGrafico = 8;

    /// <summary>Clientes na lista de cadastros recentes.</summary>
    public const int UltimosClientes = 5;

    public async Task<PainelDto> ExecutarAsync(CancellationToken cancelamento = default)
    {
        var agora = relogio.Agora;

        var cadastro = await clientes.ObterMetricasAsync(
            agora.AddDays(-DiasDaJanela), cancelamento);
        var financeiro = await painel.ObterFinanceiroAsync(agora, cancelamento);
        var receita = await painel.ReceitaMensalAsync(agora, MesesDaSerie, cancelamento);
        var cidades = await painel.ClientesPorCidadeAsync(CidadesNoGrafico, cancelamento);
        var cadastrosPorMes = await painel.CadastrosPorMesAsync(
            agora, MesesDaSerie, cancelamento);
        var recentes = await clientes.BuscarAsync(null, cancelamento);

        var entregaVersusRetirada = new PontoDoGrafico[]
        {
            new("Entrega", cadastro.TotalEntrega),
            new("Retirada", cadastro.TotalRetirada),
        };

        var ultimos = recentes
            .OrderByDescending(c => c.CriadoEm)
            .Take(UltimosClientes)
            .Select(ClienteDto.De)
            .ToList();

        return new PainelDto(
            cadastro,
            financeiro,
            new GraficosDoPainel(receita, entregaVersusRetirada, cidades, cadastrosPorMes),
            ultimos);
    }
}
