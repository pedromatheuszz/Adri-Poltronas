using AdriPoltronas.Domain.ValueObjects;
using Microsoft.EntityFrameworkCore.Storage.ValueConversion;

namespace AdriPoltronas.Infrastructure.Persistence.Configurations;

/// <summary>Conversores dos tipos de valor do dominio para as colunas existentes.</summary>
public static class ConversoresDeValor
{
    /// <summary>
    /// Dinheiro na coluna REAL.
    /// </summary>
    /// <remarks>
    /// O dominio usa <c>decimal</c> porque somar dinheiro em ponto flutuante
    /// acumula erro. A coluna, porem, e REAL: e o que o backend Python gravou
    /// desde sempre, e mudar o tipo quebraria a leitura dele. A conversao fica
    /// aqui, na borda, e nao no meio da regra.
    /// </remarks>
    public static readonly ValueConverter<Dinheiro, double> Reais =
        new(quantia => (double)quantia.Valor, bruto => Dinheiro.Reconstituir((decimal)bruto));

    /// <summary>
    /// Data simples na coluna TEXT.
    /// </summary>
    /// <remarks>
    /// Texto AAAA-MM-DD, exatamente como as consultas do backend comparam. Um
    /// valor gravado fora do formato vira data vazia na leitura, em vez de
    /// derrubar a listagem inteira por causa de uma linha antiga.
    /// </remarks>
    public static readonly ValueConverter<DataSimples, string> DataEmTexto =
        new(data => data.Texto, gravado => DataSimples.Reconstituir(gravado));
}
