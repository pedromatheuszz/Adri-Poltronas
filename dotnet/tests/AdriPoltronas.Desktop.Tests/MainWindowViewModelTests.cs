using AdriPoltronas.Application;
using AdriPoltronas.Application.Abstractions;
using AdriPoltronas.Desktop.Navigation;
using AdriPoltronas.Desktop.Servicos;
using AdriPoltronas.Desktop.ViewModels;
using AdriPoltronas.Domain.Entities;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace AdriPoltronas.Desktop.Tests;

/// <summary>Cabecalho da janela: sino de notificacoes e botao de tema.</summary>
public sealed class MainWindowViewModelTests
{
    private static readonly DateTime Agora = new(2026, 8, 28, 14, 30, 0);

    private readonly EntregasEmMemoria _entregas = new();
    private readonly PagamentosEmMemoria _pagamentos = new();
    private readonly RepositorioEmMemoria _clientes = new();
    private readonly LidasEmMemoria _lidas = new();
    private readonly TemaFalso _tema = new();

    private MainWindowViewModel CriarJanela()
    {
        var servicos = new ServiceCollection();
        servicos.AddLogging();
        servicos.AddApplication();
        servicos.AddSingleton<IEntregaRepository>(_entregas);
        servicos.AddSingleton<IPagamentoRepository>(_pagamentos);
        servicos.AddSingleton<IClienteRepository>(_clientes);
        servicos.AddSingleton<INotificacaoLidaRepository>(_lidas);
        servicos.AddSingleton<IHistoricoRepository, HistoricoEmMemoria>();
        servicos.AddSingleton<IUnidadeDeTrabalho, UnidadeSemEfeito>();
        servicos.AddSingleton<IRelogio>(new RelogioFixo());
        var provedor = servicos.BuildServiceProvider();

        return new MainWindowViewModel(
            new NavegacaoQueNaoTrocaTela(),
            new ExecutorDeCasosDeUso(provedor.GetRequiredService<IServiceScopeFactory>()),
            _tema,
            new DespachanteSincrono(),
            NullLogger<MainWindowViewModel>.Instance);
    }

    [Fact]
    public async Task OContadorDoSinoMostraAsNaoLidas()
    {
        _entregas.Semear(EntregaAgendada.Criar(1, "Ana", "2026-08-20", null, "", Agora));

        var janela = CriarJanela();
        await janela.AtualizarNotificacoesCommand.ExecuteAsync(null);

        Assert.Single(janela.Notificacoes);
        Assert.Equal(1, janela.NaoLidas);
        Assert.True(janela.TemNaoLidas);
    }

    [Fact]
    public async Task AposMarcarComoLidasOContadorZera()
    {
        // A recarga acontece de dentro do comando de marcar; se ela passasse
        // pela guarda de reentrancia, o banco registraria a leitura e o sino
        // continuaria mostrando o numero antigo.
        _entregas.Semear(EntregaAgendada.Criar(1, "Ana", "2026-08-20", null, "", Agora));

        var janela = CriarJanela();
        await janela.AtualizarNotificacoesCommand.ExecuteAsync(null);
        Assert.Equal(1, janela.NaoLidas);

        await janela.MarcarNotificacoesLidasCommand.ExecuteAsync(null);

        Assert.Equal(0, janela.NaoLidas);
        Assert.False(janela.TemNaoLidas);
        Assert.Single(janela.Notificacoes);
    }

    [Fact]
    public void OBotaoDeTemaAlternaEGuardaAEscolha()
    {
        var janela = CriarJanela();

        janela.AlternarTemaCommand.Execute(null);

        Assert.False(janela.TemaEscuro);
        Assert.Equal(1, _tema.Alternancias);
    }

    [Fact]
    public void EscFechaOPainelDeNotificacoes()
    {
        var janela = CriarJanela();
        janela.AlternarPainelDeNotificacoesCommand.Execute(null);
        Assert.True(janela.PainelDeNotificacoesAberto);

        janela.FecharPainelDeNotificacoesCommand.Execute(null);

        Assert.False(janela.PainelDeNotificacoesAberto);
    }

    [Fact]
    public void SemAlertasOPainelInformaEmVezDeFicarVazio()
    {
        var janela = CriarJanela();

        Assert.False(janela.TemNotificacoes);
    }

    /// <summary>
    /// Navegacao que so registra o destino.
    /// </summary>
    /// <remarks>
    /// A navegacao real resolve o ViewModel no container; aqui isso exigiria
    /// registrar as cinco telas e as dependencias delas, sem provar nada sobre
    /// o cabecalho.
    /// </remarks>
    private sealed class NavegacaoQueNaoTrocaTela : INavegacao
    {
        public ViewModelBase? Atual { get; private set; }

        public event Action<ViewModelBase>? Mudou;

        public void IrPara<TViewModel>() where TViewModel : ViewModelBase
        {
            Atual = null;
            _ = Mudou;
        }
    }

    private sealed class TemaFalso : ITema
    {
        public bool EstaEscuro { get; private set; } = true;

        public int Alternancias { get; private set; }

        public void Alternar()
        {
            EstaEscuro = !EstaEscuro;
            Alternancias++;
        }

        public void Restaurar()
        {
        }
    }
}
