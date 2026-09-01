using Avalonia.Controls;
using Avalonia.Interactivity;

namespace AdriPoltronas.Desktop.Views;

/// <summary>Sim ou nao, para acoes que nao podem ser desfeitas.</summary>
public partial class ConfirmacaoDialog : Window
{
    public ConfirmacaoDialog() : this("Confirmar", string.Empty)
    {
    }

    public ConfirmacaoDialog(string titulo, string pergunta)
    {
        InitializeComponent();
        Title = titulo;
        Pergunta.Text = pergunta;
    }

    private void AoConfirmar(object? remetente, RoutedEventArgs evento) => Close(true);

    private void AoNegar(object? remetente, RoutedEventArgs evento) => Close(false);
}
