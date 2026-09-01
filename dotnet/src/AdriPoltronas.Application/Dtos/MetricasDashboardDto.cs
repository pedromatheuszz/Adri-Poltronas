namespace AdriPoltronas.Application.Dtos;

/// <summary>Contagens do painel inicial.</summary>
public sealed record MetricasDashboardDto(
    int TotalClientes,
    int TotalEntrega,
    int TotalRetirada,
    int CadastrosRecentes)
{
    public static MetricasDashboardDto Vazio => new(0, 0, 0, 0);
}
