using AdriPoltronas.Domain.Entities;

namespace AdriPoltronas.Application.Dtos;

/// <summary>Alerta como o sino o exibe.</summary>
public sealed record NotificacaoDto(
    string Chave,
    string Tipo,
    string Icone,
    string Mensagem,
    string Detalhes,
    string Data,
    int Prioridade,
    bool Lida)
{
    public static NotificacaoDto De(Notificacao notificacao) => new(
        notificacao.Chave,
        notificacao.Tipo.ToString(),
        notificacao.Icone,
        notificacao.Mensagem,
        notificacao.Detalhes,
        notificacao.Data.Formatada(),
        (int)notificacao.Prioridade,
        notificacao.Lida);
}

/// <summary>Lista e contagem de nao lidas, que alimenta o contador do sino.</summary>
public sealed record PainelDeNotificacoes(
    IReadOnlyList<NotificacaoDto> Itens,
    int NaoLidas)
{
    public static PainelDeNotificacoes Vazio { get; } = new([], 0);
}
