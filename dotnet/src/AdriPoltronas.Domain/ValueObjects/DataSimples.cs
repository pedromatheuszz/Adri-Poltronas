using System.Globalization;

namespace AdriPoltronas.Domain.ValueObjects;

/// <summary>
/// Data sem hora, no formato AAAA-MM-DD.
/// </summary>
/// <remarks>
/// As colunas de vencimento, pagamento e entrega guardam texto nesse formato, e
/// as consultas comparam esse texto direto. O regex sozinho aceitava
/// "2026-13-45": o SQLite nao reclama -- <c>date()</c> sobre data impossivel
/// devolve NULL e a comparacao some em silencio. O resultado era entrega que
/// nunca aparecia nos alertas e cobranca que nunca vencia.
///
/// Por isso este tipo valida o calendario, e nao so o formato. Vazio e um
/// estado legitimo (cobranca ainda nao paga), representado por
/// <see cref="Vazia"/>.
/// </remarks>
public readonly record struct DataSimples
{
    public const string Formato = "yyyy-MM-dd";

    private DataSimples(string texto) => Texto = texto;

    /// <summary>Texto gravado. String vazia quando a data nao existe.</summary>
    public string Texto { get; }

    public bool Preenchida => !string.IsNullOrEmpty(Texto);

    public static DataSimples Vazia => new(string.Empty);

    public static DataSimples De(DateTime data) =>
        new(data.ToString(Formato, CultureInfo.InvariantCulture));

    public static bool TentarCriar(string? bruto, out DataSimples data)
    {
        var texto = bruto?.Trim() ?? string.Empty;
        if (!DateTime.TryParseExact(
                texto, Formato, CultureInfo.InvariantCulture, DateTimeStyles.None, out _))
        {
            data = default;
            return false;
        }

        data = new DataSimples(texto);
        return true;
    }

    /// <summary>Recria o gravado; texto invalido vira vazio em vez de estourar.</summary>
    public static DataSimples Reconstituir(string? gravado) =>
        TentarCriar(gravado, out var data) ? data : Vazia;

    public DateTime? ComoDateTime() =>
        DateTime.TryParseExact(
            Texto, Formato, CultureInfo.InvariantCulture, DateTimeStyles.None, out var data)
            ? data
            : null;

    /// <summary>Dias entre esta data e <paramref name="referencia"/>. Negativo = passado.</summary>
    public int? DiasAte(DateTime referencia)
    {
        var data = ComoDateTime();
        return data is null ? null : (int)(data.Value.Date - referencia.Date).TotalDays;
    }

    public string Formatada() => ComoDateTime()?.ToString("dd/MM/yyyy", CultureInfo.InvariantCulture)
                                 ?? string.Empty;

    public override string ToString() => Texto;
}
