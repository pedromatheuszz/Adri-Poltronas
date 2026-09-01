using System.Text.RegularExpressions;
using AdriPoltronas.Domain.Enums;
using AdriPoltronas.Domain.Exceptions;
using AdriPoltronas.Domain.Rules;
using AdriPoltronas.Domain.ValueObjects;

namespace AdriPoltronas.Domain.Entities;

/// <summary>
/// Entrega marcada para um cliente.
/// </summary>
/// <remarks>
/// O endpoint antigo so checava se cliente e data existiam, entao aceitava um
/// cliente inexistente e data em texto livre. A entrega era gravada e depois
/// sumia dos alertas, porque <c>date(data_entrega)</c> devolvia NULL sem erro.
/// As duas checagens agora sao invariantes da entidade.
/// </remarks>
public sealed partial class EntregaAgendada
{
    private EntregaAgendada()
    {
        ClienteNome = string.Empty;
        Descricao = string.Empty;
        HoraEntrega = string.Empty;
    }

    private EntregaAgendada(
        int clienteId,
        string clienteNome,
        DataSimples data,
        string hora,
        string descricao,
        DateTime agora)
    {
        ClienteId = clienteId;
        ClienteNome = clienteNome;
        DataEntrega = data;
        HoraEntrega = hora;
        Descricao = descricao;
        Status = StatusEntrega.Pendente;
        CriadoEm = agora;
    }

    public int Id { get; private set; }
    public int ClienteId { get; private set; }
    public string ClienteNome { get; private set; }
    public DataSimples DataEntrega { get; private set; }

    /// <summary>HH:MM, ou vazio quando so a data foi combinada.</summary>
    public string HoraEntrega { get; private set; }

    public string Descricao { get; private set; }
    public StatusEntrega Status { get; private set; }
    public DateTime CriadoEm { get; private set; }

    [GeneratedRegex(@"^([01]\d|2[0-3]):[0-5]\d$")]
    private static partial Regex FormatoDaHora();

    public static EntregaAgendada Criar(
        int clienteId,
        string? clienteNome,
        string? dataEntrega,
        string? horaEntrega,
        string? descricao,
        DateTime agora)
    {
        var erros = new List<string>();

        if (clienteId <= 0)
        {
            erros.Add("Cliente invalido.");
        }

        if (!DataSimples.TentarCriar(dataEntrega, out var data))
        {
            erros.Add(string.IsNullOrWhiteSpace(dataEntrega)
                ? "Data de entrega obrigatoria."
                : "Data de entrega invalida. Use formato AAAA-MM-DD.");
        }

        var hora = horaEntrega?.Trim() ?? string.Empty;
        if (hora.Length > 0 && !FormatoDaHora().IsMatch(hora))
        {
            erros.Add("Hora de entrega invalida. Use formato HH:MM.");
        }

        if (erros.Count > 0)
        {
            throw new ValidacaoException(erros);
        }

        return new EntregaAgendada(
            clienteId,
            TextoDoCadastro.Normalizar(clienteNome, TextoDoCadastro.NomeMaximo),
            data,
            hora,
            TextoDoCadastro.Normalizar(descricao, TextoDoCadastro.ObservacoesMaximas),
            agora);
    }

    public void Concluir()
    {
        if (Status == StatusEntrega.Cancelada)
        {
            throw new DomainException("Entrega cancelada nao pode ser concluida.");
        }

        Status = StatusEntrega.Concluida;
    }

    public void Cancelar() => Status = StatusEntrega.Cancelada;

    /// <summary>Dias ate a entrega. Negativo quando ja passou.</summary>
    public int? DiasAte(DateTime agora) => DataEntrega.DiasAte(agora);
}
