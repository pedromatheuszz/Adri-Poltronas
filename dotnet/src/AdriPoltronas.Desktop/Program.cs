using System.Globalization;
using AdriPoltronas.Application;
using AdriPoltronas.Desktop.Logging;
using AdriPoltronas.Desktop.Navigation;
using AdriPoltronas.Desktop.Servicos;
using AdriPoltronas.Desktop.ViewModels;
using AdriPoltronas.Infrastructure;
using AdriPoltronas.Infrastructure.Sistema;
using Avalonia;
using Avalonia.WebView.Desktop;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;

namespace AdriPoltronas.Desktop;

/// <summary>
/// Arranque da aplicacao e composicao das dependencias.
/// </summary>
/// <remarks>
/// Este e o unico ponto do sistema que enxerga as quatro camadas ao mesmo
/// tempo. Cada camada expoe o proprio <c>Add...</c>; aqui eles sao apenas
/// encadeados. Nenhum <c>new Repositorio(...)</c> aparece em ViewModel algum.
/// </remarks>
public static class Program
{
    /// <summary>
    /// Container da aplicacao.
    /// </summary>
    /// <remarks>
    /// Estatico porque o Avalonia instancia <see cref="App"/> por conta
    /// propria, sem passar por construtor. Fora do <see cref="App"/> ninguem
    /// resolve servico daqui: os ViewModels recebem tudo por construtor.
    /// </remarks>
    public static IServiceProvider Servicos { get; private set; } = null!;

    /// <summary>Idioma em que o sistema formata datas, numeros e moeda.</summary>
    /// <remarks>
    /// Fixado, e nao herdado do sistema operacional: a mesma base e lida pelo
    /// backend Python e por planilhas que vao para o contador. Uma maquina
    /// configurada em ingles gravaria "1,234.56" no relatorio exportado e
    /// quebraria a leitura do outro lado.
    /// </remarks>
    public const string Idioma = "pt-BR";

    [STAThread]
    public static void Main(string[] argumentos)
    {
        var cultura = CultureInfo.GetCultureInfo(Idioma);
        CultureInfo.DefaultThreadCurrentCulture = cultura;
        CultureInfo.DefaultThreadCurrentUICulture = cultura;

        Servicos = MontarContainer();
        BuildAvaloniaApp().StartWithClassicDesktopLifetime(argumentos);
    }

    // Usado pelo designer e pelas ferramentas do Avalonia.
    public static AppBuilder BuildAvaloniaApp() =>
        AppBuilder.Configure<App>()
            // Detecta Windows, Linux ou macOS em tempo de execucao: nao ha
            // caminho especifico de sistema operacional no codigo.
            .UsePlatformDetect()
            .UseDesktopWebView()
            .WithInterFont()
            .LogToTrace();

    private static IServiceProvider MontarContainer()
    {
        var configuracao = new ConfigurationBuilder()
            .SetBasePath(AppContext.BaseDirectory)
            .AddJsonFile("appsettings.json", optional: true, reloadOnChange: false)
            // Ambiente sobrepoe o arquivo: e assim que uma string de conexao do
            // PostgreSQL entra sem ficar versionada (Banco__ConexaoString).
            .AddEnvironmentVariables()
            .Build();

        var servicos = new ServiceCollection();

        servicos.AddLogging(log =>
        {
            log.AddConfiguration(configuracao.GetSection("Logging"));
            log.AddSimpleConsole();
            // O aplicativo empacotado nao tem console: sem arquivo, o log da
            // maquina do usuario se perderia.
            log.AddProvider(new ProvedorDeLogEmArquivo(LogLevel.Information));
        });

        servicos.AddApplication();
        servicos.AddInfrastructure(configuracao);

        // Apresentacao.
        servicos.AddSingleton<INavegacao, Navegacao>();
        servicos.AddSingleton<IDialogos, Dialogos>();
        servicos.AddSingleton<ExecutorDeCasosDeUso>();
        servicos.AddSingleton<IDespachante, DespachanteDoAvalonia>();
        servicos.AddSingleton<ITema, ServicoDeTema>();

        // Os ladrilhos do mapa tem cache proprio e limitam as chamadas
        // simultaneas; uma instancia por tela perderia as duas coisas.
        servicos.AddHttpClient<IFonteDeLadrilhos, FonteDeLadrilhosOsm>(cliente =>
        {
            cliente.Timeout = TimeSpan.FromSeconds(20);
            // O servico de ladrilhos recusa requisicao sem identificacao.
            cliente.DefaultRequestHeaders.UserAgent.ParseAdd("AdriPoltronas/1.0");
        });

        servicos.AddSingleton<MainWindowViewModel>();
        // As telas sao singleton: voltar ao Dashboard reaproveita o estado em
        // vez de recarregar tudo do zero a cada troca de secao.
        servicos.AddSingleton<DashboardViewModel>();
        servicos.AddSingleton<ClientesViewModel>();
        servicos.AddSingleton<MapaViewModel>();
        servicos.AddSingleton<PagamentosViewModel>();
        servicos.AddSingleton<RelatoriosViewModel>();

        return servicos.BuildServiceProvider();
    }

    /// <summary>Caminho do banco, para exibir em diagnostico.</summary>
    public static string CaminhoDoBanco() => PastaDeDados.CaminhoDoBanco();
}
