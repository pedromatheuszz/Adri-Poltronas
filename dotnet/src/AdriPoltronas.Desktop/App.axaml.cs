using AdriPoltronas.Desktop.ViewModels;
using AdriPoltronas.Desktop.Views;
using AdriPoltronas.Infrastructure.Persistence;
using Avalonia;
using Avalonia.Controls.ApplicationLifetimes;
using Avalonia.Markup.Xaml;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;

namespace AdriPoltronas.Desktop;

/// <remarks>
/// O tipo base e escrito por extenso porque o projeto tambem tem um namespace
/// chamado <c>AdriPoltronas.Application</c> -- a camada de casos de uso. Sem a
/// qualificacao, o compilador entende o namespace no lugar do tipo do Avalonia.
/// </remarks>
public partial class App : Avalonia.Application
{
    public override void Initialize() => AvaloniaXamlLoader.Load(this);

    public override void OnFrameworkInitializationCompleted()
    {
        if (ApplicationLifetime is IClassicDesktopStyleApplicationLifetime desktop)
        {
            PrepararBanco();

            var principal = Program.Servicos.GetRequiredService<MainWindowViewModel>();
            desktop.MainWindow = new MainWindow { DataContext = principal };
            principal.AoEntrar();
        }

        base.OnFrameworkInitializationCompleted();
    }

    /// <summary>
    /// Deixa o banco pronto antes de a janela abrir.
    /// </summary>
    /// <remarks>
    /// Sincrono de proposito: sem banco nao ha o que exibir, e mostrar uma
    /// tela vazia que so depois avisa do erro seria pior. A falha e registrada
    /// e a janela abre mesmo assim -- as telas exibem a mensagem na barra de
    /// status em vez de o aplicativo simplesmente nao abrir.
    /// </remarks>
    private static void PrepararBanco()
    {
        using var escopo = Program.Servicos.CreateScope();
        var log = escopo.ServiceProvider.GetRequiredService<ILogger<App>>();
        try
        {
            escopo.ServiceProvider
                .GetRequiredService<InicializadorDoBanco>()
                .PrepararAsync()
                .GetAwaiter()
                .GetResult();
        }
        catch (Exception erro)
        {
            log.LogError(erro, "Falha ao preparar o banco em {Caminho}.", Program.CaminhoDoBanco());
        }
    }
}
