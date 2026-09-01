namespace AdriPoltronas.Application.Dtos;

/// <summary>Filtros da tela de relatorios.</summary>
public sealed record FiltroDeRelatorio(
    string? Tipo = null,
    string? Cidade = null,
    string? DataInicio = null,
    string? DataFim = null);

/// <summary>Uma linha do relatorio de clientes.</summary>
public sealed record LinhaDoRelatorio(
    int Id,
    string Nome,
    string Cidade,
    string Bairro,
    string Tipo,
    string CriadoEm);

/// <summary>Resultado da consulta, com os totais que o rodape exibe.</summary>
public sealed record RelatorioDto(
    IReadOnlyList<LinhaDoRelatorio> Linhas,
    int Total,
    int TotalEntrega,
    int TotalRetirada)
{
    public static RelatorioDto Vazio { get; } = new([], 0, 0, 0);
}

/// <summary>Concentracao de clientes por cidade.</summary>
public sealed record DesempenhoDaRegiao(
    string Cidade,
    int Clientes,
    int Entregas,
    int Retiradas,
    double PercentualDaBase);
