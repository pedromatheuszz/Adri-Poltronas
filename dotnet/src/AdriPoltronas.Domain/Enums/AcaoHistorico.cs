namespace AdriPoltronas.Domain.Enums;

/// <summary>O que aconteceu com o cliente.</summary>
/// <remarks>
/// Os textos gravados sao os que a tabela <c>historico</c> ja usa, em caixa
/// alta e sem acento -- ha 40 registros historicos com esses valores, e mudar
/// a grafia deixaria o passado invisivel para qualquer filtro.
/// </remarks>
public enum AcaoHistorico
{
    Criacao = 0,
    Atualizacao = 1,
    Exclusao = 2,
    Importacao = 3,
}

public static class AcaoHistoricoExtensions
{
    public static string ParaTexto(this AcaoHistorico acao) => acao switch
    {
        AcaoHistorico.Criacao => "CRIACAO",
        AcaoHistorico.Atualizacao => "ATUALIZACAO",
        AcaoHistorico.Exclusao => "EXCLUSAO",
        AcaoHistorico.Importacao => "IMPORTACAO",
        _ => acao.ToString().ToUpperInvariant(),
    };

    public static AcaoHistorico DoTexto(string? texto) => texto?.Trim().ToUpperInvariant() switch
    {
        "ATUALIZACAO" => AcaoHistorico.Atualizacao,
        "EXCLUSAO" => AcaoHistorico.Exclusao,
        "IMPORTACAO" => AcaoHistorico.Importacao,
        _ => AcaoHistorico.Criacao,
    };
}
