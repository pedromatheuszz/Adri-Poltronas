using AdriPoltronas.Application;
using AdriPoltronas.Application.Abstractions;
using AdriPoltronas.Application.Dtos;
using AdriPoltronas.Desktop.Navigation;
using AdriPoltronas.Desktop.Servicos;
using AdriPoltronas.Desktop.ViewModels;
using AdriPoltronas.Domain.Entities;
using AdriPoltronas.Domain.Enums;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace AdriPoltronas.Desktop.Tests;

/// <summary>
/// Comportamento da tela de clientes, sem abrir janela.
/// </summary>
/// <remarks>
/// Os ViewModels sao testaveis porque nao dependem de nada concreto da
/// interface: dialogo e despachante chegam como interface, e os casos de uso
/// vem do container. E o que permite verificar o fluxo da tela em
/// milissegundos, em vez de dirigir a janela na mao.
/// </remarks>
public sealed class ClientesViewModelTests
{
    private readonly RepositorioEmMemoria _repositorio = new();
    private readonly DialogosFalsos _dialogos = new();

    private ClientesViewModel CriarTela()
    {
        var servicos = new ServiceCollection();
        servicos.AddLogging();
        servicos.AddApplication();
        servicos.AddSingleton<IClienteRepository>(_repositorio);
        servicos.AddSingleton<IHistoricoRepository, HistoricoEmMemoria>();
        servicos.AddSingleton<IUnidadeDeTrabalho, UnidadeSemEfeito>();
        servicos.AddSingleton<IRelogio>(new RelogioFixo());
        var provedor = servicos.BuildServiceProvider();

        return new ClientesViewModel(
            new ExecutorDeCasosDeUso(provedor.GetRequiredService<IServiceScopeFactory>()),
            _dialogos,
            new DespachanteSincrono(),
            NullLogger<ClientesViewModel>.Instance);
    }

    [Fact]
    public async Task AoEntrar_CarregaAListaDeClientes()
    {
        _repositorio.Semear("Ana Paula", "Gloria");
        var tela = CriarTela();

        await tela.RecarregarCommand.ExecuteAsync(null);

        Assert.Single(tela.Clientes);
        Assert.Equal("Ana Paula", tela.Clientes[0].Nome);
    }

    [Fact]
    public async Task AposCadastrar_AListaMostraONovoCliente()
    {
        // Regressao. A recarga que roda dentro do comando de cadastro passava
        // pela mesma guarda de reentrancia do proprio comando: encontrava
        // Ocupado = true e saia calada. O cliente ia para o banco e a tela
        // continuava sem ele -- sem erro nenhum na interface.
        var tela = CriarTela();
        await tela.RecarregarCommand.ExecuteAsync(null);
        Assert.Empty(tela.Clientes);

        _dialogos.ProximoFormulario = new DadosDoCliente(
            "Cliente Novo", "89230-210", "Rua A", "Centro", "Joinville", "Entrega", "");

        await tela.NovoCommand.ExecuteAsync(null);

        Assert.Single(tela.Clientes);
        Assert.Equal("Cliente Novo", tela.Clientes[0].Nome);
    }

    [Fact]
    public async Task AoCancelarOFormulario_NadaEGravado()
    {
        var tela = CriarTela();
        _dialogos.ProximoFormulario = null;

        await tela.NovoCommand.ExecuteAsync(null);

        Assert.Empty(tela.Clientes);
    }

    [Fact]
    public async Task CadastroInvalido_MostraOErroENaoGrava()
    {
        var tela = CriarTela();
        _dialogos.ProximoFormulario = new DadosDoCliente(
            "Cliente", "cep-errado", "Rua A", "Centro", "Joinville", "Entrega", "");

        await tela.NovoCommand.ExecuteAsync(null);

        Assert.Empty(tela.Clientes);
        Assert.Contains("CEP", tela.Mensagem, StringComparison.Ordinal);
    }

    [Fact]
    public async Task Excluir_PedeConfirmacaoEParaSeORespondeForNao()
    {
        _repositorio.Semear("Ana Paula", "Gloria");
        var tela = CriarTela();
        await tela.RecarregarCommand.ExecuteAsync(null);
        tela.Selecionado = tela.Clientes[0];
        _dialogos.Confirmacao = false;

        await tela.ExcluirCommand.ExecuteAsync(null);

        Assert.True(_dialogos.PerguntouConfirmacao);
        Assert.Single(tela.Clientes);
    }

    [Fact]
    public async Task Excluir_ConfirmadoRemoveDaLista()
    {
        _repositorio.Semear("Ana Paula", "Gloria");
        var tela = CriarTela();
        await tela.RecarregarCommand.ExecuteAsync(null);
        tela.Selecionado = tela.Clientes[0];
        _dialogos.Confirmacao = true;

        await tela.ExcluirCommand.ExecuteAsync(null);

        Assert.Empty(tela.Clientes);
        Assert.Equal("Cliente excluido.", tela.Mensagem);
    }

    [Fact]
    public async Task Excluir_SemSelecao_AvisaENaoAbreConfirmacao()
    {
        var tela = CriarTela();

        await tela.ExcluirCommand.ExecuteAsync(null);

        Assert.False(_dialogos.PerguntouConfirmacao);
        Assert.Equal("Selecione um cliente.", tela.Mensagem);
    }

    [Fact]
    public async Task Buscar_FiltraPeloTermoDigitado()
    {
        _repositorio.Semear("Ana Paula", "Gloria");
        _repositorio.Semear("Bruno Lima", "Centro");
        var tela = CriarTela();

        tela.TermoDeBusca = "Bruno";
        // O ViewModel adia a consulta; sem a espera, o teste leria a lista
        // antes de a busca acontecer.
        await Task.Delay(ClientesViewModel.AtrasoDaBusca + TimeSpan.FromMilliseconds(200));

        Assert.Single(tela.Clientes);
        Assert.Equal("Bruno Lima", tela.Clientes[0].Nome);
    }

    // ------------------------------------------------------------------ dublês

    private sealed class DialogosFalsos : IDialogos
    {
        public DadosDoCliente? ProximoFormulario { get; set; }
        public bool Confirmacao { get; set; }
        public bool PerguntouConfirmacao { get; private set; }

        public Task<DadosDoCliente?> EditarClienteAsync(ClienteDto? existente) =>
            Task.FromResult(ProximoFormulario);

        public Task<bool> ConfirmarAsync(string titulo, string pergunta)
        {
            PerguntouConfirmacao = true;
            return Task.FromResult(Confirmacao);
        }

        // Os dialogos abaixo nao participam dos casos testados aqui; devolvem o
        // valor de "cancelado", que e o desfecho neutro.
        public Task<DadosDoPagamento?> NovoPagamentoAsync(IReadOnlyList<ClienteDto> clientes) =>
            Task.FromResult<DadosDoPagamento?>(null);

        public Task MostrarCobrancaAsync(PagamentoDto pagamento) => Task.CompletedTask;

        public Task<string?> EscolherArquivoParaSalvarAsync(
            string titulo, string nomeSugerido, FormatoDeArquivo formato) =>
            Task.FromResult<string?>(null);

        public Task<string?> EscolherArquivoParaAbrirAsync(string titulo) =>
            Task.FromResult<string?>(null);
    }

}
