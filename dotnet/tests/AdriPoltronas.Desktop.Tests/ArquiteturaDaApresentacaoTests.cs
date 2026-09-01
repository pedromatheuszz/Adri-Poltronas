using System.Reflection;
using AdriPoltronas.Desktop.ViewModels;
using Xunit;

namespace AdriPoltronas.Desktop.Tests;

/// <summary>
/// Fronteira entre apresentacao e o resto do sistema.
/// </summary>
/// <remarks>
/// O projeto Desktop referencia a Infrastructure -- precisa, para registrar as
/// dependencias no arranque. Isso deixa o caminho aberto para um ViewModel
/// injetar um <c>DbContext</c> "so desta vez", e a partir dai a camada de
/// apresentacao volta a falar com o banco. Estes testes fecham esse caminho.
/// </remarks>
public sealed class ArquiteturaDaApresentacaoTests
{
    private static IEnumerable<Type> ViewModels() =>
        typeof(ClientesViewModel).Assembly
            .GetTypes()
            .Where(tipo => typeof(ViewModelBase).IsAssignableFrom(tipo) && !tipo.IsAbstract);

    [Fact]
    public void NenhumViewModelRecebeTipoDeInfraestrutura()
    {
        var infracoes = new List<string>();

        foreach (var viewModel in ViewModels())
        {
            foreach (var construtor in viewModel.GetConstructors())
            {
                foreach (var parametro in construtor.GetParameters())
                {
                    var espaco = parametro.ParameterType.Namespace ?? string.Empty;
                    if (espaco.StartsWith("AdriPoltronas.Infrastructure", StringComparison.Ordinal) ||
                        espaco.StartsWith("Microsoft.EntityFrameworkCore", StringComparison.Ordinal))
                    {
                        infracoes.Add($"{viewModel.Name}({parametro.ParameterType.Name})");
                    }
                }
            }
        }

        Assert.True(
            infracoes.Count == 0,
            $"ViewModel dependendo de infraestrutura: {string.Join(", ", infracoes)}");
    }

    [Fact]
    public void ViewModelsDependemDeAbstracoesENaoDeImplementacoes()
    {
        // Dialogo e navegacao entram por interface; a implementacao concreta,
        // que conhece Window, so e amarrada no registro de dependencias.
        var construtor = typeof(ClientesViewModel).GetConstructors().Single();
        var tipos = construtor.GetParameters().Select(p => p.ParameterType).ToList();

        Assert.Contains(tipos, tipo => tipo.Name == "IDialogos");
        Assert.Contains(tipos, tipo => tipo.Name == "IDespachante");
        Assert.DoesNotContain(tipos, tipo => tipo.Name == "Dialogos");
    }

    [Fact]
    public void CodeBehindDasViewsNaoCarregaLogica()
    {
        // O code-behind deve ser minimo. O unico com metodos proprios e o
        // dialogo, que precisa fechar a janela devolvendo um valor -- para isso
        // nao existe binding.
        var views = typeof(ClientesViewModel).Assembly
            .GetTypes()
            .Where(tipo => tipo.Namespace == "AdriPoltronas.Desktop.Views");

        foreach (var view in views)
        {
            var proprios = view
                .GetMethods(BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic |
                            BindingFlags.DeclaredOnly)
                .Where(metodo => !metodo.IsSpecialGetterOuSetter())
                .Where(metodo => metodo.Name != "InitializeComponent")
                .ToList();

            Assert.True(
                proprios.Count <= 3,
                $"{view.Name} tem {proprios.Count} metodos proprios; code-behind deve ser minimo.");
        }
    }
}

internal static class ReflexaoExtensions
{
    public static bool IsSpecialGetterOuSetter(this MethodInfo metodo) => metodo.IsSpecialName;
}
