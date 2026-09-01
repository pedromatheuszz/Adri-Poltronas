using System.Text.RegularExpressions;

namespace AdriPoltronas.Domain.ValueObjects;

/// <summary>
/// CEP brasileiro, sempre no formato canonico 00000-000.
/// </summary>
/// <remarks>
/// E um value object porque a normalizacao precisa acontecer em um lugar so.
/// Com string solta, "89230210" e "89230-210" viravam dois clientes distintos
/// na deteccao de duplicados da importacao, e a geocodificacao do mapa
/// consultava o ViaCEP duas vezes para o mesmo endereco.
/// </remarks>
public readonly partial record struct Cep
{
    private Cep(string valor) => Valor = valor;

    public string Valor { get; }

    [GeneratedRegex(@"^\d{5}-?\d{3}$")]
    private static partial Regex Formato();

    /// <summary>Aceita com ou sem hifen; devolve false se nao for um CEP.</summary>
    public static bool TentarCriar(string? bruto, out Cep cep)
    {
        var texto = bruto?.Trim() ?? string.Empty;
        if (!Formato().IsMatch(texto))
        {
            cep = default;
            return false;
        }

        var digitos = texto.Replace("-", string.Empty);
        cep = new Cep($"{digitos[..5]}-{digitos[5..]}");
        return true;
    }

    /// <summary>
    /// Recria a partir do que esta gravado, sem validar.
    /// </summary>
    /// <remarks>
    /// A base tem cadastros anteriores a esta regra, com CEP em branco ou fora
    /// do formato. Validar na leitura faria a listagem inteira falhar por causa
    /// deles; a validacao acontece na escrita, via <see cref="TentarCriar"/>.
    /// </remarks>
    public static Cep Reconstituir(string? gravado) =>
        TentarCriar(gravado, out var cep) ? cep : new Cep(gravado?.Trim() ?? string.Empty);

    public override string ToString() => Valor;
}
