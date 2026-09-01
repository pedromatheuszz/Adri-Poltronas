namespace AdriPoltronas.Domain.Enums;

/// <summary>Como o cliente recebe a poltrona.</summary>
/// <remarks>
/// Persistido como texto ("Entrega"/"Retirada"), e nao como inteiro: e assim
/// que a coluna <c>clientes.entrega_retirada</c> ja existe no banco em uso, e
/// converter para int quebraria o backend Python enquanto ele ainda le a mesma
/// base. Ver <see cref="TipoAtendimentoExtensions"/>.
/// </remarks>
public enum TipoAtendimento
{
    Entrega = 0,
    Retirada = 1,
}

public static class TipoAtendimentoExtensions
{
    public const string TextoEntrega = "Entrega";
    public const string TextoRetirada = "Retirada";

    public static string ParaTexto(this TipoAtendimento tipo) =>
        tipo == TipoAtendimento.Retirada ? TextoRetirada : TextoEntrega;

    /// <summary>Converte o texto do banco. Devolve false para qualquer outro valor.</summary>
    public static bool TentarConverter(string? texto, out TipoAtendimento tipo)
    {
        switch (texto?.Trim())
        {
            case TextoEntrega:
                tipo = TipoAtendimento.Entrega;
                return true;
            case TextoRetirada:
                tipo = TipoAtendimento.Retirada;
                return true;
            default:
                tipo = TipoAtendimento.Entrega;
                return false;
        }
    }
}
