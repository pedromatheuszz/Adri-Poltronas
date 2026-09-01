namespace AdriPoltronas.Application.Dtos;

/// <summary>
/// Resumo financeiro do painel.
/// </summary>
/// <remarks>
/// Reproduz os cartoes que a interface web sempre mostrou. A variacao vem
/// pronta do caso de uso porque a mesma conta aparecia em dois lugares na
/// interface antiga e as duas divergiam quando o mes anterior era zero.
/// </remarks>
public sealed record MetricasFinanceirasDto(
    decimal FaturamentoDoMes,
    decimal FaturamentoDoMesAnterior,
    double VariacaoPercentual,
    int QuantidadeDeRecebimentosNoMes,
    decimal TicketMedioDoMes,
    decimal AReceber,
    decimal EmAtraso,
    int QuantidadeEmAtraso)
{
    public static MetricasFinanceirasDto Vazio { get; } = new(0, 0, 0, 0, 0, 0, 0, 0);
}

/// <summary>Um ponto de uma serie temporal ou uma barra de um grafico.</summary>
public sealed record PontoDoGrafico(string Rotulo, double Valor);

/// <summary>Conjunto de graficos do painel.</summary>
public sealed record GraficosDoPainel(
    IReadOnlyList<PontoDoGrafico> ReceitaMensal,
    IReadOnlyList<PontoDoGrafico> EntregaVersusRetirada,
    IReadOnlyList<PontoDoGrafico> ClientesPorCidade,
    IReadOnlyList<PontoDoGrafico> CadastrosPorMes)
{
    public static GraficosDoPainel Vazio { get; } = new([], [], [], []);
}

/// <summary>
/// Tudo que o painel precisa, montado numa chamada so.
/// </summary>
/// <remarks>
/// A interface antiga fazia cinco requisicoes para desenhar a tela inicial.
/// Aqui e uma unidade: a tela nao chega a existir num estado em que metade
/// dos cartoes ja carregou e a outra metade nao.
/// </remarks>
public sealed record PainelDto(
    MetricasDashboardDto Cadastro,
    MetricasFinanceirasDto Financeiro,
    GraficosDoPainel Graficos,
    IReadOnlyList<ClienteDto> UltimosClientes)
{
    public static PainelDto Vazio { get; } = new(
        MetricasDashboardDto.Vazio,
        MetricasFinanceirasDto.Vazio,
        GraficosDoPainel.Vazio,
        []);
}
