namespace AdriPoltronas.Domain.Enums;

/// <summary>Situacao de uma entrega agendada.</summary>
public enum StatusEntrega
{
    Pendente = 0,
    Concluida = 1,
    Cancelada = 2,
}

public static class StatusEntregaExtensions
{
    public static string ParaTexto(this StatusEntrega status) => status switch
    {
        StatusEntrega.Concluida => "Concluida",
        StatusEntrega.Cancelada => "Cancelada",
        _ => "Pendente",
    };

    public static bool TentarConverter(string? texto, out StatusEntrega status)
    {
        switch (texto?.Trim())
        {
            case "Pendente": status = StatusEntrega.Pendente; return true;
            case "Concluida": status = StatusEntrega.Concluida; return true;
            case "Cancelada": status = StatusEntrega.Cancelada; return true;
            default: status = StatusEntrega.Pendente; return false;
        }
    }

    public static StatusEntrega DoTexto(string? texto) =>
        TentarConverter(texto, out var status) ? status : StatusEntrega.Pendente;
}
