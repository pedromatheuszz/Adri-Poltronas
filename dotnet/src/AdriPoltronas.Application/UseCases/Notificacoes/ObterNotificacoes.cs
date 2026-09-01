using AdriPoltronas.Application.Abstractions;
using AdriPoltronas.Application.Dtos;
using AdriPoltronas.Domain.Entities;

namespace AdriPoltronas.Application.UseCases.Notificacoes;

/// <summary>
/// Monta a lista de alertas do sino.
/// </summary>
/// <remarks>
/// As notificacoes nao sao gravadas: sao derivadas de entregas, cobrancas e
/// clientes a cada consulta. O backend antigo fazia isso em SQL, com os
/// limiares escritos dentro da consulta; aqui a leitura traz so o que esta
/// dentro da janela e as regras ficam em <see cref="RegrasDeNotificacao"/>,
/// testaveis sem banco.
/// </remarks>
public sealed class ObterNotificacoes(
    IEntregaRepository entregas,
    IPagamentoRepository pagamentos,
    IClienteRepository clientes,
    INotificacaoLidaRepository lidas,
    IRelogio relogio)
{
    public async Task<PainelDeNotificacoes> ExecutarAsync(
        CancellationToken cancelamento = default)
    {
        var agora = relogio.Agora;
        var limite = agora.Date.AddDays(RegrasDeNotificacao.DiasDeAntecedencia);

        var entregasProximas = await entregas.PendentesAteAsync(limite, cancelamento);
        var cobrancasAVencer = await pagamentos.AVencerAteAsync(agora.Date, cancelamento);
        var todosOsClientes = await clientes.BuscarAsync(null, cancelamento);
        var chavesLidas = await lidas.ChavesLidasAsync(cancelamento);

        var alertas = new List<Notificacao>();
        alertas.AddRange(entregasProximas
            .Select(e => RegrasDeNotificacao.DeEntrega(e, agora))
            .Take(RegrasDeNotificacao.MaximoPorTipo));

        alertas.AddRange(cobrancasAVencer
            .Select(p => RegrasDeNotificacao.DePagamento(p, agora))
            .Take(RegrasDeNotificacao.MaximoPorTipo));

        // O teto vale tambem para clientes inativos. Sem ele, uma base madura
        // enche o painel de milhares de itens remontados a cada atualizacao.
        alertas.AddRange(todosOsClientes
            .Where(c => (agora.Date - c.AtualizadoEm.Date).TotalDays
                        >= RegrasDeNotificacao.DiasParaClienteInativo)
            .OrderBy(c => c.AtualizadoEm)
            .Take(RegrasDeNotificacao.MaximoPorTipo)
            .Select(c => RegrasDeNotificacao.DeClienteInativo(c, agora)));

        var ordenados = alertas
            .Select(a => a.ComoLida(chavesLidas.Contains(a.Chave)))
            .OrderByDescending(a => a.Prioridade)
            .ThenBy(a => a.Data.Texto)
            .Select(NotificacaoDto.De)
            .ToList();

        return new PainelDeNotificacoes(ordenados, ordenados.Count(n => !n.Lida));
    }
}

/// <summary>Registra que o operador dispensou os alertas informados.</summary>
public sealed class MarcarNotificacoesLidas(INotificacaoLidaRepository lidas)
{
    public Task ExecutarAsync(
        IReadOnlyCollection<string> chaves, CancellationToken cancelamento = default) =>
        chaves.Count == 0
            ? Task.CompletedTask
            : lidas.MarcarComoLidasAsync(chaves, cancelamento);
}
