using AdriPoltronas.Application.Dtos;

namespace AdriPoltronas.Application.Abstractions;

/// <summary>
/// Consultas de leitura do painel e dos relatorios.
/// </summary>
/// <remarks>
/// Separada dos repositorios de entidade de proposito: nenhuma destas
/// consultas devolve entidade, sao somas e contagens que precisam acontecer no
/// banco. Junta-las ao repositorio de cobrancas misturaria acesso a agregado
/// com relatorio, e as duas mudam por motivos diferentes.
/// </remarks>
public interface IDashboardRepository
{
    /// <summary>Numeros financeiros do mes que contem a data de referencia.</summary>
    Task<MetricasFinanceirasDto> ObterFinanceiroAsync(
        DateTime referencia, CancellationToken cancelamento = default);

    /// <summary>Receita por mes, do mais antigo ao mais recente, meses sem receita zerados.</summary>
    Task<IReadOnlyList<PontoDoGrafico>> ReceitaMensalAsync(
        DateTime referencia, int meses, CancellationToken cancelamento = default);

    Task<IReadOnlyList<PontoDoGrafico>> ClientesPorCidadeAsync(
        int maximo, CancellationToken cancelamento = default);

    Task<IReadOnlyList<PontoDoGrafico>> CadastrosPorMesAsync(
        DateTime referencia, int meses, CancellationToken cancelamento = default);

    /// <summary>Concentracao por cidade, para a aba de relatorios.</summary>
    Task<IReadOnlyList<DesempenhoDaRegiao>> DesempenhoPorRegiaoAsync(
        CancellationToken cancelamento = default);

    /// <summary>Clientes que atendem aos filtros do relatorio, ja em forma de linha.</summary>
    /// <remarks>
    /// Nao devolve entidade porque nada aqui vai ser alterado -- e leitura para
    /// exibir e exportar. Trazer agregados carregaria o rastreamento do EF para
    /// milhares de registros sem necessidade.
    /// </remarks>
    Task<IReadOnlyList<LinhaDoRelatorio>> ClientesDoRelatorioAsync(
        FiltroDeRelatorio filtro, CancellationToken cancelamento = default);
}
