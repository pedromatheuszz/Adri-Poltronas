using Avalonia.Controls;
using Avalonia.Controls.Templates;
using AdriPoltronas.Desktop.ViewModels;

namespace AdriPoltronas.Desktop;

/// <summary>
/// Encontra a View de um ViewModel por convencao de nome.
/// </summary>
/// <remarks>
/// <c>ClientesViewModel</c> resolve para <c>Views.ClientesView</c>. E o que
/// mantem a navegacao trabalhando so com ViewModels: sem isto, algum ponto do
/// codigo precisaria instanciar o controle concreto e a fronteira entre
/// apresentacao e logica de tela se perderia.
/// </remarks>
public sealed class ViewLocator : IDataTemplate
{
    public Control Build(object? dados)
    {
        if (dados is null)
        {
            return new TextBlock { Text = "Nada a exibir." };
        }

        var nomeDaView = dados.GetType().FullName!
            .Replace("ViewModels.", "Views.", StringComparison.Ordinal)
            .Replace("ViewModel", "View", StringComparison.Ordinal);

        var tipo = Type.GetType(nomeDaView);
        return tipo is not null
            ? (Control)Activator.CreateInstance(tipo)!
            : new TextBlock { Text = $"View nao encontrada: {nomeDaView}" };
    }

    public bool Match(object? dados) => dados is ViewModelBase;
}
