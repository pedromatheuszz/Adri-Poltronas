using Microsoft.EntityFrameworkCore.Storage.ValueConversion;

namespace AdriPoltronas.Infrastructure.Persistence.Configurations;

/// <summary>
/// Conversao de data compativel com o que ja esta gravado no banco.
/// </summary>
/// <remarks>
/// O SQLite nao tem tipo de data: as colunas guardam texto produzido por
/// <c>datetime('now','localtime')</c>, no formato <c>yyyy-MM-dd HH:mm:ss</c>.
///
/// O conversor padrao do EF grava fracao de segundo e o "T" do ISO-8601. Os
/// filtros do backend Python comparam essas colunas como texto
/// (<c>criado_em &gt;= datetime('now','-30 days')</c>), e um formato diferente
/// ordena diferente: cadastros feitos pelo aplicativo .NET sumiriam das
/// metricas calculadas pelo Python. Enquanto as duas pilhas dividem a mesma
/// base, o formato precisa ser identico.
/// </remarks>
public static class ConversoresDeData
{
    public const string Formato = "yyyy-MM-dd HH:mm:ss";

    public static readonly ValueConverter<DateTime, string> TextoLocal = new(
        data => data.ToString(Formato, System.Globalization.CultureInfo.InvariantCulture),
        texto => Ler(texto));

    private static DateTime Ler(string texto) =>
        DateTime.TryParse(
            texto,
            System.Globalization.CultureInfo.InvariantCulture,
            System.Globalization.DateTimeStyles.None,
            out var data)
            ? data
            // Registro com data vazia ou corrompida nao pode derrubar a
            // listagem inteira; vira o minimo e aparece como cadastro antigo.
            : DateTime.MinValue;
}
