using AdriPoltronas.Domain.Enums;
using AdriPoltronas.Domain.ValueObjects;

namespace AdriPoltronas.Domain.Entities;

/// <summary>
/// Alerta derivado do estado do sistema.
/// </summary>
/// <remarks>
/// Nao e persistida: cada notificacao e uma leitura de entregas, clientes e
/// pagamentos feita na hora. So o estado de "lida" vai para o banco, pela
/// <see cref="Chave"/> -- que precisa ser estavel entre execucoes, senao o
/// alerta que o operador dispensou reaparece na proxima abertura.
///
/// A montagem fica no Domain, e nao numa consulta SQL, porque "entrega
/// atrasada" e "cliente inativo" sao definicoes do negocio -- e agora
/// testaveis sem banco.
/// </remarks>
public sealed record Notificacao(
    TipoNotificacao Tipo,
    string Chave,
    PrioridadeNotificacao Prioridade,
    string Icone,
    string Mensagem,
    string Detalhes,
    DataSimples Data,
    int? ClienteId = null,
    int? EntregaId = null,
    int? PagamentoId = null)
{
    /// <summary>Marcada como lida pelo operador. Preenchido na leitura.</summary>
    public bool Lida { get; init; }

    public Notificacao ComoLida(bool lida) => this with { Lida = lida };
}

/// <summary>
/// Regras que definem cada alerta.
/// </summary>
/// <remarks>
/// Os limiares estavam embutidos no SQL. Aqui viram constantes com nome, que e
/// onde alguem procura quando pergunta "a partir de quantos dias um cliente e
/// considerado inativo?".
/// </remarks>
public static class RegrasDeNotificacao
{
    /// <summary>Janela de "entrega proxima", em dias.</summary>
    public const int DiasDeAntecedencia = 3;

    /// <summary>Sem atualizacao por este periodo, o cliente vira alerta.</summary>
    public const int DiasParaClienteInativo = 90;

    /// <summary>
    /// Teto por categoria.
    /// </summary>
    /// <remarks>
    /// A de clientes inativos nao tinha limite: cresce com a base inteira, e
    /// numa base madura o painel virava milhares de itens remontados a cada
    /// atualizacao.
    /// </remarks>
    public const int MaximoPorTipo = 50;

    public static Notificacao DeEntrega(EntregaAgendada entrega, DateTime agora)
    {
        var dias = entrega.DiasAte(agora) ?? 0;
        var hora = string.IsNullOrEmpty(entrega.HoraEntrega)
            ? string.Empty
            : $" as {entrega.HoraEntrega}";

        return dias switch
        {
            < 0 => new Notificacao(
                TipoNotificacao.EntregaAtrasada,
                $"entrega_atrasada:{entrega.Id}",
                PrioridadeNotificacao.Critica,
                "\U0001F6A8",
                $"ENTREGA ATRASADA: {entrega.ClienteNome} (era {entrega.DataEntrega.Texto})",
                entrega.Descricao,
                entrega.DataEntrega,
                EntregaId: entrega.Id),

            0 => new Notificacao(
                TipoNotificacao.EntregaHoje,
                $"entrega_hoje:{entrega.Id}",
                PrioridadeNotificacao.Alta,
                "\U0001F4E6",
                $"Entrega agendada para HOJE: {entrega.ClienteNome}{hora}",
                entrega.Descricao,
                entrega.DataEntrega,
                EntregaId: entrega.Id),

            _ => new Notificacao(
                TipoNotificacao.EntregaProxima,
                $"entrega_proxima:{entrega.Id}",
                PrioridadeNotificacao.Media,
                "\U0001F4CB",
                $"Entrega proxima: {entrega.ClienteNome} em {entrega.DataEntrega.Texto}",
                entrega.Descricao,
                entrega.DataEntrega,
                EntregaId: entrega.Id),
        };
    }

    public static Notificacao DeClienteInativo(Cliente cliente, DateTime agora)
    {
        var dias = (int)(agora.Date - cliente.AtualizadoEm.Date).TotalDays;
        return new Notificacao(
            TipoNotificacao.ClienteInativo,
            $"cliente_inativo:{cliente.Id}",
            PrioridadeNotificacao.Baixa,
            "\U0001F464",
            $"{cliente.Nome} sem atualizacao ha {dias} dias",
            cliente.Endereco.Cidade,
            DataSimples.De(cliente.AtualizadoEm),
            ClienteId: cliente.Id);
    }

    public static Notificacao DePagamento(Pagamento pagamento, DateTime agora)
    {
        var vencido = pagamento.EstaEmAtraso(agora);
        var valor = pagamento.Valor.Formatado();

        return vencido
            ? new Notificacao(
                TipoNotificacao.PagamentoAtrasado,
                $"pagamento_atrasado:{pagamento.Id}",
                PrioridadeNotificacao.Alta,
                "\U0001F4B0",
                $"Pagamento {valor} de {pagamento.ClienteNome} atrasado!",
                $"Vencimento: {pagamento.DataVencimento.Texto}",
                pagamento.DataVencimento,
                PagamentoId: pagamento.Id)
            : new Notificacao(
                TipoNotificacao.PagamentoHoje,
                $"pagamento_hoje:{pagamento.Id}",
                PrioridadeNotificacao.Media,
                "\U0001F4B3",
                $"Pagamento {valor} de {pagamento.ClienteNome} vence HOJE!",
                string.Empty,
                pagamento.DataVencimento,
                PagamentoId: pagamento.Id);
    }
}
