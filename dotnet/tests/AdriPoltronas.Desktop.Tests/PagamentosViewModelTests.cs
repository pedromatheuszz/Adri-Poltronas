using AdriPoltronas.Application;
using AdriPoltronas.Application.Abstractions;
using AdriPoltronas.Application.Dtos;
using AdriPoltronas.Desktop.Navigation;
using AdriPoltronas.Desktop.Servicos;
using AdriPoltronas.Desktop.ViewModels;
using AdriPoltronas.Domain.Entities;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace AdriPoltronas.Desktop.Tests;

/// <summary>Fluxo da aba financeira, sem abrir janela.</summary>
public sealed class PagamentosViewModelTests
{
    private static readonly DateTime Agora = new(2026, 8, 28, 14, 30, 0);

    private readonly PagamentosEmMemoria _pagamentos = new();
    private readonly RepositorioEmMemoria _clientes = new();
    private readonly DialogosDePagamento _dialogos = new();

    private PagamentosViewModel CriarTela()
    {
        var servicos = new ServiceCollection();
        servicos.AddLogging();
        servicos.AddApplication();
        servicos.AddSingleton<IPagamentoRepository>(_pagamentos);
        servicos.AddSingleton<IClienteRepository>(_clientes);
        servicos.AddSingleton<IHistoricoRepository, HistoricoEmMemoria>();
        servicos.AddSingleton<IUnidadeDeTrabalho, UnidadeSemEfeito>();
        servicos.AddSingleton<IRelogio>(new RelogioFixo());
        var provedor = servicos.BuildServiceProvider();

        return new PagamentosViewModel(
            new ExecutorDeCasosDeUso(provedor.GetRequiredService<IServiceScopeFactory>()),
            _dialogos,
            new DespachanteSincrono(),
            NullLogger<PagamentosViewModel>.Instance);
    }

    [Fact]
    public async Task AoEntrarCarregaListaETotais()
    {
        _pagamentos.Semear(Pagamento.Criar(
            1, "Ana", 100m, "", "2026-09-10", "Pix", "Recebido", "2026-08-10", Agora));

        var tela = CriarTela();
        await tela.RecarregarCommand.ExecuteAsync(null);

        Assert.Single(tela.Pagamentos);
        Assert.Equal(100m, tela.Metricas.TotalRecebido);
        Assert.False(tela.ListaVazia);
    }

    [Fact]
    public async Task AposRegistrarAListaMostraOLancamento()
    {
        // Mesma armadilha da tela de clientes: a recarga nao pode passar pela
        // guarda de reentrancia, senao o lancamento entra no banco e a lista
        // continua vazia.
        var cliente = _clientes.Semear(Cliente.Criar(
            "Ana Souza", "89230-210", "Rua A", "Centro", "Joinville", "Entrega", "", Agora));

        _dialogos.ProximoFormulario = new DadosDoPagamento(
            cliente.Id, cliente.Nome, 250m, "Poltrona", "2026-09-10", "Pix", "Pendente", null);

        var tela = CriarTela();
        await tela.NovoCommand.ExecuteAsync(null);

        Assert.Single(tela.Pagamentos);
        Assert.Equal("Ana Souza", tela.Pagamentos[0].ClienteNome);
    }

    [Fact]
    public async Task SemClienteCadastradoOFormularioNemAbre()
    {
        var tela = CriarTela();

        await tela.NovoCommand.ExecuteAsync(null);

        Assert.False(_dialogos.AbriuFormulario);
        Assert.Contains("Cadastre um cliente", tela.Mensagem, StringComparison.Ordinal);
    }

    [Fact]
    public async Task ConfirmarSemSelecaoAvisaEmVezDeEstourar()
    {
        var tela = CriarTela();

        await tela.ConfirmarCommand.ExecuteAsync(null);

        Assert.Contains("Selecione", tela.Mensagem, StringComparison.Ordinal);
    }

    [Fact]
    public async Task ConfirmarAtualizaOStatusNaLista()
    {
        _pagamentos.Semear(Pagamento.Criar(
            1, "Ana", 100m, "", "2026-09-10", "Pix", "Pendente", null, Agora));

        var tela = CriarTela();
        await tela.RecarregarCommand.ExecuteAsync(null);
        tela.Selecionado = tela.Pagamentos[0];

        await tela.ConfirmarCommand.ExecuteAsync(null);

        Assert.Equal("Recebido", tela.Pagamentos[0].Status);
    }

    [Fact]
    public async Task CancelarRecebidoMostraOMotivoDoDominio()
    {
        _pagamentos.Semear(Pagamento.Criar(
            1, "Ana", 100m, "", "2026-09-10", "Pix", "Recebido", "2026-08-10", Agora));

        var tela = CriarTela();
        await tela.RecarregarCommand.ExecuteAsync(null);
        tela.Selecionado = tela.Pagamentos[0];

        await tela.CancelarCommand.ExecuteAsync(null);

        Assert.Contains("estorno", tela.Mensagem, StringComparison.OrdinalIgnoreCase);
        Assert.Equal("Recebido", tela.Pagamentos[0].Status);
    }

    [Fact]
    public async Task ExcluirPedeConfirmacaoAntes()
    {
        _pagamentos.Semear(Pagamento.Criar(
            1, "Ana", 100m, "", "2026-09-10", "Pix", "Pendente", null, Agora));

        var tela = CriarTela();
        await tela.RecarregarCommand.ExecuteAsync(null);
        tela.Selecionado = tela.Pagamentos[0];
        _dialogos.Confirmacao = false;

        await tela.ExcluirCommand.ExecuteAsync(null);

        Assert.True(_dialogos.PerguntouConfirmacao);
        Assert.Single(tela.Pagamentos);
    }

    [Fact]
    public async Task FiltroDeStatusReduzALista()
    {
        _pagamentos.Semear(Pagamento.Criar(
            1, "Ana", 100m, "", "2026-09-10", "Pix", "Recebido", "2026-08-10", Agora));
        _pagamentos.Semear(Pagamento.Criar(
            1, "Bruno", 50m, "", "2026-09-10", "Pix", "Pendente", null, Agora));

        var tela = CriarTela();
        await tela.RecarregarCommand.ExecuteAsync(null);
        Assert.Equal(2, tela.Pagamentos.Count);

        tela.FiltroDeStatus = "Recebido";
        await tela.RecarregarCommand.ExecuteAsync(null);

        Assert.Single(tela.Pagamentos);
    }
}
