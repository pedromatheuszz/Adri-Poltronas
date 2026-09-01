using AdriPoltronas.Application.Dtos;
using AdriPoltronas.Domain.Entities;

namespace AdriPoltronas.Application.Abstractions;

/// <summary>
/// Acesso ao cadastro de clientes.
/// </summary>
/// <remarks>
/// Declarada aqui, implementada em Infrastructure: e assim que a Application
/// fica sem saber que existe Entity Framework, e os testes de caso de uso
/// rodam sem banco nenhum.
///
/// Nao e um <c>IRepository&lt;T&gt;</c> generico de proposito -- os metodos
/// sao os que o aplicativo realmente usa, cada um com a assinatura que faz
/// sentido para ele.
/// </remarks>
public interface IClienteRepository
{
    /// <summary>Lista, opcionalmente filtrando por nome, cidade ou bairro.</summary>
    Task<IReadOnlyList<Cliente>> BuscarAsync(string? termo, CancellationToken cancelamento = default);

    Task<Cliente?> ObterPorIdAsync(int id, CancellationToken cancelamento = default);

    /// <summary>Marca o cliente para inclusao. So grava no <see cref="IUnidadeDeTrabalho"/>.</summary>
    void Adicionar(Cliente cliente);

    void Remover(Cliente cliente);

    /// <summary>Contagens do painel, calculadas no banco.</summary>
    /// <param name="inicioDaJanela">Limite inferior para "cadastros recentes".</param>
    Task<MetricasDashboardDto> ObterMetricasAsync(
        DateTime inicioDaJanela, CancellationToken cancelamento = default);
}
