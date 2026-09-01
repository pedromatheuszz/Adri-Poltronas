using AdriPoltronas.Application.Abstractions;
using AdriPoltronas.Application.Dtos;
using AdriPoltronas.Domain.Entities;
using AdriPoltronas.Domain.Enums;
using Microsoft.EntityFrameworkCore;

namespace AdriPoltronas.Infrastructure.Persistence.Repositories;

/// <inheritdoc cref="IPagamentoRepository"/>
public sealed class PagamentoRepository(AdriPoltronasDbContext contexto, IRelogio relogio)
    : IPagamentoRepository
{
    public async Task<IReadOnlyList<Pagamento>> BuscarAsync(
        FiltroDePagamentos filtro, CancellationToken cancelamento = default)
    {
        var consulta = contexto.Pagamentos.AsQueryable();

        var cliente = filtro.Cliente?.Trim();
        if (!string.IsNullOrEmpty(cliente))
        {
            consulta = consulta.Where(p => EF.Functions.Like(p.ClienteNome, $"%{cliente}%"));
        }

        if (StatusPagamentoExtensions.TentarConverter(filtro.Status, out var status))
        {
            consulta = consulta.Where(p => p.Status == status);
        }

        return await consulta
            .OrderByDescending(p => p.Id)
            .AsNoTracking()
            .ToListAsync(cancelamento);
    }

    public Task<Pagamento?> ObterPorIdAsync(int id, CancellationToken cancelamento = default) =>
        contexto.Pagamentos.FirstOrDefaultAsync(p => p.Id == id, cancelamento);

    public async Task<IReadOnlyList<Pagamento>> AVencerAteAsync(
        DateTime limite, CancellationToken cancelamento = default)
    {
        // O filtro por data acontece em memoria: a coluna guarda texto e o
        // tipo do dominio nao e comparavel em LINQ. A varredura, porem, ja vem
        // reduzida as pendentes -- que sao poucas por definicao, porque
        // cobranca recebida sai do conjunto.
        var pendentes = await contexto.Pagamentos
            .Where(p => p.Status == StatusPagamento.Pendente ||
                        p.Status == StatusPagamento.Atrasado)
            .AsNoTracking()
            .ToListAsync(cancelamento);

        return [.. pendentes
            .Where(p => p.DataVencimento.DiasAte(limite) is <= 0)
            .OrderBy(p => p.DataVencimento.Texto)];
    }

    public void Adicionar(Pagamento pagamento) => contexto.Pagamentos.Add(pagamento);

    public void Remover(Pagamento pagamento) => contexto.Pagamentos.Remove(pagamento);

    public async Task<MetricasPagamentosDto> ObterMetricasAsync(
        CancellationToken cancelamento = default)
    {
        var agora = relogio.Agora;

        // Projecao de tres campos, sem rastreamento: o somatorio nao pode ir
        // para o SQL porque valor e status passam por conversor, e um SUM sobre
        // coluna convertida nao e traduzivel.
        var linhas = await contexto.Pagamentos
            .Select(p => new { p.Status, p.Valor, p.DataVencimento })
            .AsNoTracking()
            .ToListAsync(cancelamento);

        var recebidos = linhas.Where(l => l.Status == StatusPagamento.Recebido).ToList();
        var abertos = linhas
            .Where(l => l.Status is StatusPagamento.Pendente or StatusPagamento.Atrasado)
            .ToList();
        var atrasados = abertos.Where(l => l.DataVencimento.DiasAte(agora) is < 0).ToList();

        return new MetricasPagamentosDto(
            recebidos.Sum(l => l.Valor.Valor),
            abertos.Sum(l => l.Valor.Valor),
            atrasados.Sum(l => l.Valor.Valor),
            recebidos.Count,
            abertos.Count);
    }
}
