using AdriPoltronas.Application.Abstractions;
using AdriPoltronas.Application.Common;
using AdriPoltronas.Application.Dtos;
using AdriPoltronas.Application.UseCases.Dados;
using AdriPoltronas.Application.UseCases.Notificacoes;
using AdriPoltronas.Domain.Entities;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace AdriPoltronas.Application.Tests;

public sealed class ObterNotificacoesTests
{
    private static readonly DateTime Agora = new(2026, 8, 28, 10, 0, 0);

    private readonly RepositorioFalsoDeEntregas _entregas = new();
    private readonly RepositorioFalsoDePagamentos _pagamentos = new();
    private readonly RepositorioFalsoDeClientes _clientes = new();
    private readonly RepositorioFalsoDeNotificacoesLidas _lidas = new();

    private ObterNotificacoes Caso() =>
        new(_entregas, _pagamentos, _clientes, _lidas, new RelogioFalso(Agora));

    [Fact]
    public async Task EntregaAtrasadaVemAntesDeClienteInativo()
    {
        _entregas.Semear(EntregaAgendada.Criar(1, "Ana", "2026-08-10", null, "", Agora));
        _clientes.Semear(Cliente.Criar(
            "Antigo", "89230-210", "Rua", "Centro", "Joinville", "Entrega", "",
            Agora.AddDays(-200)));

        var painel = await Caso().ExecutarAsync();

        Assert.Equal(2, painel.Itens.Count);
        Assert.Equal("EntregaAtrasada", painel.Itens[0].Tipo);
    }

    [Fact]
    public async Task ClienteAtualizadoRecentementeNaoViraAlerta()
    {
        _clientes.Semear(Cliente.Criar(
            "Recente", "89230-210", "Rua", "Centro", "Joinville", "Entrega", "",
            Agora.AddDays(-10)));

        var painel = await Caso().ExecutarAsync();

        Assert.Empty(painel.Itens);
    }

    [Fact]
    public async Task ChaveJaDispensadaNaoContaComoNaoLida()
    {
        var entrega = _entregas.Semear(
            EntregaAgendada.Criar(1, "Ana", "2026-08-10", null, "", Agora));
        await _lidas.MarcarComoLidasAsync([$"entrega_atrasada:{entrega.Id}"]);

        var painel = await Caso().ExecutarAsync();

        Assert.Single(painel.Itens);
        Assert.True(painel.Itens[0].Lida);
        Assert.Equal(0, painel.NaoLidas);
    }

    [Fact]
    public async Task MarcarLidasSemChaveNaoChamaOBanco()
    {
        var caso = new MarcarNotificacoesLidas(_lidas);

        await caso.ExecutarAsync([]);

        Assert.Empty(await _lidas.ChavesLidasAsync());
    }
}

public sealed class ImportarClientesTests
{
    private static readonly DateTime Agora = new(2026, 8, 28, 10, 0, 0);

    [Fact]
    public async Task LinhaInvalidaNaoDerrubaOLote()
    {
        var importador = new ImportadorFalso(
        [
            new LinhaImportada(2, new DadosDoCliente(
                "Ana Souza", "89230-210", "Rua A", "Centro", "Joinville", "Entrega", "")),
            new LinhaImportada(3, new DadosDoCliente(
                "", "89230-210", "Rua B", "Centro", "Joinville", "Entrega", "")),
        ]);

        var clientes = new RepositorioFalsoDeClientes();
        var unidade = new UnidadeDeTrabalhoFalsa();
        var caso = new ImportarClientes(
            importador, clientes, new RepositorioFalsoDeHistorico(), unidade,
            new RelogioFalso(Agora), NullLogger<ImportarClientes>.Instance);

        var resultado = await caso.ExecutarAsync("planilha.csv");

        Assert.True(resultado.Sucesso);
        Assert.Equal(1, resultado.Valor!.Importados);
        Assert.Single(resultado.Valor.Rejeitadas);
        Assert.Equal(3, resultado.Valor.Rejeitadas[0].Numero);
        // Tudo numa transacao so: importar metade e o pior desfecho possivel.
        Assert.Equal(1, unidade.Confirmacoes);
    }

    [Fact]
    public async Task LoteTodoInvalidoNaoAbreTransacao()
    {
        var importador = new ImportadorFalso(
        [
            new LinhaImportada(2, new DadosDoCliente("", "", "", "", "", "", "")),
        ]);

        var unidade = new UnidadeDeTrabalhoFalsa();
        var caso = new ImportarClientes(
            importador, new RepositorioFalsoDeClientes(), new RepositorioFalsoDeHistorico(),
            unidade, new RelogioFalso(Agora), NullLogger<ImportarClientes>.Instance);

        var resultado = await caso.ExecutarAsync("planilha.csv");

        Assert.Equal(0, resultado.Valor!.Importados);
        Assert.Equal(0, unidade.Confirmacoes);
    }

    private sealed class ImportadorFalso(IReadOnlyList<LinhaImportada> linhas)
        : IImportadorDePlanilha
    {
        public Task<Resultado<IReadOnlyList<LinhaImportada>>> LerAsync(
            string caminho, CancellationToken cancelamento = default) =>
            Task.FromResult(Resultado<IReadOnlyList<LinhaImportada>>.Ok(linhas));
    }
}
