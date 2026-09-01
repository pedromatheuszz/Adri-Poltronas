namespace AdriPoltronas.Domain.Enums;

/// <summary>Situacao de uma cobranca.</summary>
/// <remarks>
/// Persistido como texto, igual as demais colunas de status: e o que a tabela
/// `pagamentos` ja contem e o que as consultas financeiras comparam.
/// </remarks>
public enum StatusPagamento
{
    Pendente = 0,
    Recebido = 1,
    Atrasado = 2,
    Cancelado = 3,
}

public static class StatusPagamentoExtensions
{
    public static string ParaTexto(this StatusPagamento status) => status switch
    {
        StatusPagamento.Recebido => "Recebido",
        StatusPagamento.Atrasado => "Atrasado",
        StatusPagamento.Cancelado => "Cancelado",
        _ => "Pendente",
    };

    public static bool TentarConverter(string? texto, out StatusPagamento status)
    {
        switch (texto?.Trim())
        {
            case "Pendente": status = StatusPagamento.Pendente; return true;
            case "Recebido": status = StatusPagamento.Recebido; return true;
            case "Atrasado": status = StatusPagamento.Atrasado; return true;
            case "Cancelado": status = StatusPagamento.Cancelado; return true;
            default: status = StatusPagamento.Pendente; return false;
        }
    }

    public static StatusPagamento DoTexto(string? texto) =>
        TentarConverter(texto, out var status) ? status : StatusPagamento.Pendente;
}
