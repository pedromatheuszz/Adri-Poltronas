using System.Globalization;
using AdriPoltronas.Application.Abstractions;
using AdriPoltronas.Application.Dtos;
using AdriPoltronas.Domain.Enums;
using Microsoft.EntityFrameworkCore;

namespace AdriPoltronas.Infrastructure.Persistence.Repositories;

/// <summary>
/// Consultas de leitura do painel e dos relatorios.
/// </summary>
/// <remarks>
/// Os somatorios financeiros sao feitos em memoria sobre uma projecao estreita,
/// e nao em SQL. O motivo e concreto: valor e datas passam por conversor de
/// valor, e SUM ou GROUP BY sobre coluna convertida nao e traduzivel pelo EF.
/// A alternativa seria SQL cru especifico do SQLite, que amarraria o painel ao
/// provedor. No volume de uma revenda, milhares de lancamentos, a projecao de
/// quatro campos custa milissegundos; se um dia deixar de custar, a troca fica
/// contida nesta classe.
/// </remarks>
public sealed class DashboardRepository(AdriPoltronasDbContext contexto) : IDashboardRepository
{
    private static readonly CultureInfo Brasil = CultureInfo.GetCultureInfo("pt-BR");

    public async Task<MetricasFinanceirasDto> ObterFinanceiroAsync(
        DateTime referencia, CancellationToken cancelamento = default)
    {
        var lancamentos = await LancamentosAsync(cancelamento);

        var mes = InicioDoMes(referencia);
        var mesAnterior = mes.AddMonths(-1);

        var recebidosNoMes = lancamentos
            .Where(l => l.Status == StatusPagamento.Recebido && NoMes(l.Receita, mes))
            .ToList();
        var faturamento = recebidosNoMes.Sum(l => l.Valor);

        var faturamentoAnterior = lancamentos
            .Where(l => l.Status == StatusPagamento.Recebido && NoMes(l.Receita, mesAnterior))
            .Sum(l => l.Valor);

        var abertos = lancamentos
            .Where(l => l.Status is StatusPagamento.Pendente or StatusPagamento.Atrasado)
            .ToList();
        var vencidos = abertos.Where(l => l.Vencimento < referencia.Date).ToList();

        return new MetricasFinanceirasDto(
            faturamento,
            faturamentoAnterior,
            Variacao(faturamento, faturamentoAnterior),
            recebidosNoMes.Count,
            recebidosNoMes.Count == 0 ? 0 : Math.Round(faturamento / recebidosNoMes.Count, 2),
            abertos.Sum(l => l.Valor),
            vencidos.Sum(l => l.Valor),
            vencidos.Count);
    }

    public async Task<IReadOnlyList<PontoDoGrafico>> ReceitaMensalAsync(
        DateTime referencia, int meses, CancellationToken cancelamento = default)
    {
        var lancamentos = await LancamentosAsync(cancelamento);
        var recebidos = lancamentos.Where(l => l.Status == StatusPagamento.Recebido).ToList();

        // Meses sem receita entram zerados: um grafico que pula o mes vazio
        // sugere um crescimento que nao houve.
        return [.. JanelaDeMeses(referencia, meses).Select(mes => new PontoDoGrafico(
            RotuloDoMes(mes),
            (double)recebidos.Where(l => NoMes(l.Receita, mes)).Sum(l => l.Valor)))];
    }

    public async Task<IReadOnlyList<PontoDoGrafico>> ClientesPorCidadeAsync(
        int maximo, CancellationToken cancelamento = default)
    {
        // Este agrupamento vai inteiro para o banco: cidade e coluna de texto
        // simples, sem conversor no caminho.
        var cidades = await contexto.Clientes
            .Where(c => c.Endereco.Cidade != string.Empty)
            .GroupBy(c => c.Endereco.Cidade)
            .Select(grupo => new { Cidade = grupo.Key, Total = grupo.Count() })
            .OrderByDescending(item => item.Total)
            .Take(maximo)
            .AsNoTracking()
            .ToListAsync(cancelamento);

        return [.. cidades.Select(c => new PontoDoGrafico(c.Cidade, c.Total))];
    }

    public async Task<IReadOnlyList<PontoDoGrafico>> CadastrosPorMesAsync(
        DateTime referencia, int meses, CancellationToken cancelamento = default)
    {
        var janela = JanelaDeMeses(referencia, meses).ToList();
        var inicio = janela[0];

        // Aqui o corte vai para o SQL: criado_em e texto no formato
        // "AAAA-MM-DD HH:MM:SS", que ordena igual a data que representa.
        var datas = await contexto.Clientes
            .AsNoTracking()
            .Where(c => c.CriadoEm >= inicio)
            .Select(c => c.CriadoEm)
            .ToListAsync(cancelamento);

        return [.. janela.Select(mes => new PontoDoGrafico(
            RotuloDoMes(mes),
            datas.Count(data => NoMes(data, mes))))];
    }

    public async Task<IReadOnlyList<DesempenhoDaRegiao>> DesempenhoPorRegiaoAsync(
        CancellationToken cancelamento = default)
    {
        var porCidade = await contexto.Clientes
            .Where(c => c.Endereco.Cidade != string.Empty)
            .GroupBy(c => c.Endereco.Cidade)
            .Select(grupo => new
            {
                Cidade = grupo.Key,
                Total = grupo.Count(),
                Entregas = grupo.Count(c => c.Tipo == TipoAtendimento.Entrega),
            })
            .AsNoTracking()
            .ToListAsync(cancelamento);

        var totalDaBase = porCidade.Sum(item => item.Total);

        return [.. porCidade
            .OrderByDescending(item => item.Total)
            .Select(item => new DesempenhoDaRegiao(
                item.Cidade,
                item.Total,
                item.Entregas,
                item.Total - item.Entregas,
                totalDaBase == 0 ? 0 : Math.Round(item.Total * 100.0 / totalDaBase, 1)))];
    }

    public async Task<IReadOnlyList<LinhaDoRelatorio>> ClientesDoRelatorioAsync(
        FiltroDeRelatorio filtro, CancellationToken cancelamento = default)
    {
        var consulta = contexto.Clientes.AsQueryable();

        if (TipoAtendimentoExtensions.TentarConverter(filtro.Tipo, out var tipo))
        {
            consulta = consulta.Where(c => c.Tipo == tipo);
        }

        var cidade = filtro.Cidade?.Trim();
        if (!string.IsNullOrEmpty(cidade))
        {
            consulta = consulta.Where(c => EF.Functions.Like(c.Endereco.Cidade, $"%{cidade}%"));
        }

        if (TentarData(filtro.DataInicio, out var inicio))
        {
            consulta = consulta.Where(c => c.CriadoEm >= inicio);
        }

        if (TentarData(filtro.DataFim, out var fim))
        {
            // Fim inclusivo: quem escolhe "ate dia 30" espera o dia 30 inteiro.
            var limite = fim.Date.AddDays(1);
            consulta = consulta.Where(c => c.CriadoEm < limite);
        }

        var encontrados = await consulta
            .OrderBy(c => c.Nome)
            .AsNoTracking()
            .ToListAsync(cancelamento);

        return [.. encontrados.Select(c => new LinhaDoRelatorio(
            c.Id,
            c.Nome,
            c.Endereco.Cidade,
            c.Endereco.Bairro,
            c.Tipo.ParaTexto(),
            c.CriadoEm.ToString("dd/MM/yyyy", CultureInfo.InvariantCulture)))];
    }

    private async Task<IReadOnlyList<Lancamento>> LancamentosAsync(CancellationToken cancelamento)
    {
        var linhas = await contexto.Pagamentos
            .Select(p => new { p.Status, p.Valor, p.DataPagamento, p.DataVencimento, p.CriadoEm })
            .AsNoTracking()
            .ToListAsync(cancelamento);

        return [.. linhas.Select(l => new Lancamento(
            l.Status,
            l.Valor.Valor,
            // Espelha COALESCE(NULLIF(data_pagamento, ''), criado_em) do backend
            // Python: cobranca marcada como recebida sem data cai na data de
            // criacao, e nao some da serie mensal.
            l.DataPagamento.ComoDateTime() ?? l.CriadoEm.Date,
            l.DataVencimento.ComoDateTime() ?? DateTime.MaxValue.Date))];
    }

    private static bool TentarData(string? bruto, out DateTime data) =>
        DateTime.TryParseExact(
            bruto?.Trim(), "yyyy-MM-dd", CultureInfo.InvariantCulture,
            DateTimeStyles.None, out data);

    private static DateTime InicioDoMes(DateTime data) => new(data.Year, data.Month, 1);

    private static bool NoMes(DateTime data, DateTime mes) =>
        data.Year == mes.Year && data.Month == mes.Month;

    /// <summary>Os N meses que terminam no mes de referencia, do mais antigo ao atual.</summary>
    private static IEnumerable<DateTime> JanelaDeMeses(DateTime referencia, int meses)
    {
        var total = Math.Max(meses, 1);
        var primeiro = InicioDoMes(referencia).AddMonths(-(total - 1));
        return Enumerable.Range(0, total).Select(passo => primeiro.AddMonths(passo));
    }

    private static string RotuloDoMes(DateTime mes) => mes.ToString("MMM/yy", Brasil);

    /// <summary>Variacao percentual; base zero devolve zero em vez de infinito.</summary>
    private static double Variacao(decimal atual, decimal anterior) =>
        anterior == 0 ? 0 : Math.Round((double)((atual - anterior) / anterior) * 100, 1);

    private readonly record struct Lancamento(
        StatusPagamento Status, decimal Valor, DateTime Receita, DateTime Vencimento);
}
