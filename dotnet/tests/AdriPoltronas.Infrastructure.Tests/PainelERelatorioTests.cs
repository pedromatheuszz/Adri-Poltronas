using AdriPoltronas.Application.Dtos;
using AdriPoltronas.Domain.Entities;
using AdriPoltronas.Infrastructure.Persistence.Repositories;
using Microsoft.EntityFrameworkCore;
using Xunit;

namespace AdriPoltronas.Infrastructure.Tests;

/// <summary>Consultas de leitura do painel e dos relatorios.</summary>
public sealed class PainelERelatorioTests : IDisposable
{
    private static readonly DateTime Agora = new(2026, 8, 28, 10, 0, 0);

    private readonly BancoLegado _banco = new();

    [Fact]
    public async Task PainelSeparaOMesAtualDoAnterior()
    {
        await using (var contexto = _banco.AbrirContexto())
        {
            contexto.Pagamentos.AddRange(
                Pagamento.Criar(1, "A", 300m, "", "2026-08-10", "Pix", "Recebido",
                    "2026-08-10", Agora),
                Pagamento.Criar(1, "A", 200m, "", "2026-07-10", "Pix", "Recebido",
                    "2026-07-10", Agora));
            await contexto.SaveChangesAsync();
        }

        await using var leitura = _banco.AbrirContexto();
        var painel = new DashboardRepository(leitura);

        var financeiro = await painel.ObterFinanceiroAsync(Agora);

        Assert.Equal(300m, financeiro.FaturamentoDoMes);
        Assert.Equal(200m, financeiro.FaturamentoDoMesAnterior);
        Assert.Equal(50, financeiro.VariacaoPercentual);
        Assert.Equal(300m, financeiro.TicketMedioDoMes);
    }

    [Fact]
    public async Task MesAnteriorZeradoNaoGeraVariacaoInfinita()
    {
        await using (var contexto = _banco.AbrirContexto())
        {
            contexto.Pagamentos.Add(Pagamento.Criar(
                1, "A", 300m, "", "2026-08-10", "Pix", "Recebido", "2026-08-10", Agora));
            await contexto.SaveChangesAsync();
        }

        await using var leitura = _banco.AbrirContexto();
        var financeiro = await new DashboardRepository(leitura).ObterFinanceiroAsync(Agora);

        Assert.Equal(0, financeiro.VariacaoPercentual);
    }

    [Fact]
    public async Task RecebidoSemDataCaiNoMesDaCriacao()
    {
        // Espelha COALESCE(NULLIF(data_pagamento,''), criado_em) do backend:
        // sem isso a cobranca antiga sumiria da serie mensal.
        await using (var contexto = _banco.AbrirContexto())
        {
            var pagamento = Pagamento.Criar(
                1, "A", 150m, "", "2026-08-10", "Pix", "Pendente", null, Agora);
            contexto.Pagamentos.Add(pagamento);
            await contexto.SaveChangesAsync();

            await contexto.Database.ExecuteSqlRawAsync(
                "UPDATE pagamentos SET status = 'Recebido', data_pagamento = ''");
        }

        await using var leitura = _banco.AbrirContexto();
        var financeiro = await new DashboardRepository(leitura).ObterFinanceiroAsync(Agora);

        Assert.Equal(150m, financeiro.FaturamentoDoMes);
    }

    [Fact]
    public async Task SerieMensalZeraOsMesesSemReceita()
    {
        await using var contexto = _banco.AbrirContexto();
        var serie = await new DashboardRepository(contexto).ReceitaMensalAsync(Agora, 6);

        Assert.Equal(6, serie.Count);
        Assert.All(serie, ponto => Assert.Equal(0, ponto.Valor));
    }

    [Fact]
    public async Task RelatorioRespeitaOFiltroDeTipoEDeData()
    {
        _banco.InserirComoOPythonInsere(
            "Ana", "89230-210", "Rua A", "Centro", "Joinville", "Entrega",
            "2026-08-01 09:00:00");
        _banco.InserirComoOPythonInsere(
            "Bruno", "89230-210", "Rua B", "Centro", "Joinville", "Retirada",
            "2026-06-01 09:00:00");

        await using var contexto = _banco.AbrirContexto();
        var linhas = await new DashboardRepository(contexto).ClientesDoRelatorioAsync(
            new FiltroDeRelatorio("Entrega", null, "2026-07-01", "2026-08-31"));

        Assert.Single(linhas);
        Assert.Equal("Ana", linhas[0].Nome);
    }

    [Fact]
    public async Task DataFimEInclusiva()
    {
        _banco.InserirComoOPythonInsere(
            "Ana", "89230-210", "Rua A", "Centro", "Joinville", "Entrega",
            "2026-08-31 23:10:00");

        await using var contexto = _banco.AbrirContexto();
        var linhas = await new DashboardRepository(contexto).ClientesDoRelatorioAsync(
            new FiltroDeRelatorio(null, null, null, "2026-08-31"));

        Assert.Single(linhas);
    }

    [Fact]
    public async Task DesempenhoPorRegiaoSomaCemPorCento()
    {
        _banco.InserirComoOPythonInsere(
            "Ana", "89230-210", "Rua A", "Centro", "Joinville", "Entrega",
            "2026-08-01 09:00:00");
        _banco.InserirComoOPythonInsere(
            "Bruno", "89230-210", "Rua B", "Centro", "Blumenau", "Retirada",
            "2026-08-01 09:00:00");

        await using var contexto = _banco.AbrirContexto();
        var regioes = await new DashboardRepository(contexto).DesempenhoPorRegiaoAsync();

        Assert.Equal(2, regioes.Count);
        Assert.Equal(100, regioes.Sum(r => r.PercentualDaBase));
    }

    public void Dispose() => _banco.Dispose();
}
