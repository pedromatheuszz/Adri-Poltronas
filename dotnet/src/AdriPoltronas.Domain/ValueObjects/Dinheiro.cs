using System.Globalization;

namespace AdriPoltronas.Domain.ValueObjects;

/// <summary>
/// Valor em reais.
/// </summary>
/// <remarks>
/// <c>decimal</c>, e nao <c>double</c>: dinheiro somado em ponto flutuante
/// binario acumula erro, e o faturamento do mes e uma soma de dezenas de
/// parcelas. A coluna do banco e REAL, e a conversao acontece na borda, no
/// mapeamento -- nao no meio da regra de negocio.
///
/// Os limites vieram de <c>validators.py</c>: abaixo de um centavo nao e
/// cobranca, e meio milhao e um teto que denuncia digito a mais.
/// </remarks>
public readonly record struct Dinheiro
{
    public const decimal Minimo = 0.01m;
    public const decimal Maximo = 500_000.00m;

    private Dinheiro(decimal valor) => Valor = valor;

    public decimal Valor { get; }

    public static Dinheiro Zero => new(0m);

    public static bool TentarCriar(decimal bruto, out Dinheiro dinheiro)
    {
        var arredondado = Math.Round(bruto, 2, MidpointRounding.AwayFromZero);
        if (arredondado < Minimo || arredondado > Maximo)
        {
            dinheiro = default;
            return false;
        }

        dinheiro = new Dinheiro(arredondado);
        return true;
    }

    /// <summary>Recria o que ja esta gravado, sem validar limites.</summary>
    /// <remarks>
    /// Ha cobrancas anteriores a estas regras na base. Validar na leitura faria
    /// a lista inteira falhar por causa delas.
    /// </remarks>
    public static Dinheiro Reconstituir(decimal gravado) =>
        new(Math.Round(gravado, 2, MidpointRounding.AwayFromZero));

    /// <summary>Formato brasileiro, como a interface web sempre exibiu.</summary>
    public string Formatado() =>
        Valor.ToString("C2", CultureInfo.GetCultureInfo("pt-BR"));

    public static Dinheiro operator +(Dinheiro a, Dinheiro b) => new(a.Valor + b.Valor);

    public override string ToString() => Formatado();
}
