namespace AdriPoltronas.Domain.Enums;

/// <summary>Como o cliente paga.</summary>
public enum TipoPagamento
{
    Pix = 0,
    Boleto = 1,
    Dinheiro = 2,
    Cartao = 3,
    Outro = 4,
}

public static class TipoPagamentoExtensions
{
    /// <summary>Formas que a integracao com o Asaas emite; as outras sao manuais.</summary>
    public static bool EmitidoPeloAsaas(this TipoPagamento tipo) =>
        tipo is TipoPagamento.Pix or TipoPagamento.Boleto;

    public static string ParaTexto(this TipoPagamento tipo) => tipo switch
    {
        TipoPagamento.Boleto => "Boleto",
        TipoPagamento.Dinheiro => "Dinheiro",
        TipoPagamento.Cartao => "Cartao",
        TipoPagamento.Outro => "Outro",
        _ => "Pix",
    };

    public static bool TentarConverter(string? texto, out TipoPagamento tipo)
    {
        switch (texto?.Trim())
        {
            case "Pix": tipo = TipoPagamento.Pix; return true;
            case "Boleto": tipo = TipoPagamento.Boleto; return true;
            case "Dinheiro": tipo = TipoPagamento.Dinheiro; return true;
            case "Cartao": tipo = TipoPagamento.Cartao; return true;
            case "Outro": tipo = TipoPagamento.Outro; return true;
            default: tipo = TipoPagamento.Pix; return false;
        }
    }

    public static TipoPagamento DoTexto(string? texto) =>
        TentarConverter(texto, out var tipo) ? tipo : TipoPagamento.Pix;
}
