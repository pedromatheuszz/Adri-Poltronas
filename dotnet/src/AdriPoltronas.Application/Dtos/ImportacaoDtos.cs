namespace AdriPoltronas.Application.Dtos;

/// <summary>
/// O que uma importacao produziu.
/// </summary>
/// <remarks>
/// Importar cadastro em lote quase nunca da certo por inteiro: uma linha sem
/// nome, um CEP com letra. Por isso o resultado nao e um booleano -- as linhas
/// boas entram e as rejeitadas voltam com o motivo, para o operador corrigir
/// na planilha em vez de adivinhar.
/// </remarks>
public sealed record ResultadoDaImportacao(
    int Importados,
    IReadOnlyList<LinhaRejeitada> Rejeitadas)
{
    public int Total => Importados + Rejeitadas.Count;

    public static ResultadoDaImportacao Nenhum { get; } = new(0, []);
}

/// <summary>Linha que a importacao recusou, com o motivo.</summary>
public sealed record LinhaRejeitada(int Numero, string Conteudo, string Motivo);

/// <summary>Formatos aceitos na importacao e na exportacao.</summary>
public enum FormatoDeArquivo
{
    Csv = 0,
    Xlsx = 1,
    Json = 2,
}
