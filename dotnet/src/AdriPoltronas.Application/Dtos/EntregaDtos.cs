using AdriPoltronas.Domain.Entities;
using AdriPoltronas.Domain.Enums;

namespace AdriPoltronas.Application.Dtos;

/// <summary>Entrega agendada como a agenda a exibe.</summary>
public sealed record EntregaDto(
    int Id,
    int ClienteId,
    string ClienteNome,
    string DataEntrega,
    string DataFormatada,
    string HoraEntrega,
    string Descricao,
    string Status,
    int? DiasAte)
{
    /// <summary>Venceu e continua pendente.</summary>
    public bool EmAtraso => Status == "Pendente" && DiasAte is < 0;

    public static EntregaDto De(EntregaAgendada entrega, DateTime agora) => new(
        entrega.Id,
        entrega.ClienteId,
        entrega.ClienteNome,
        entrega.DataEntrega.Texto,
        entrega.DataEntrega.Formatada(),
        entrega.HoraEntrega,
        entrega.Descricao,
        entrega.Status.ParaTexto(),
        entrega.DiasAte(agora));
}

/// <summary>O que o formulario de agendamento envia.</summary>
public sealed record DadosDaEntrega(
    int ClienteId,
    string? ClienteNome,
    string? DataEntrega,
    string? HoraEntrega,
    string? Descricao);
