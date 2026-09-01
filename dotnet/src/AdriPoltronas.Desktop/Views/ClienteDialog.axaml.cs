using AdriPoltronas.Application.Dtos;
using AdriPoltronas.Desktop.ViewModels;
using Avalonia.Controls;
using Avalonia.Interactivity;

namespace AdriPoltronas.Desktop.Views;

/// <summary>
/// Formulario de cliente.
/// </summary>
/// <remarks>
/// Este e o unico code-behind com codigo alem do <c>InitializeComponent</c>, e
/// so porque fechar a janela devolvendo um valor e responsabilidade da propria
/// janela -- nao existe binding para <c>Close(resultado)</c>. Nenhuma regra de
/// negocio passa por aqui: os dois manipuladores so decidem o que devolver.
/// </remarks>
public partial class ClienteDialog : Window
{
    public ClienteDialog() : this(null)
    {
    }

    public ClienteDialog(ClienteDto? existente)
    {
        InitializeComponent();
        DataContext = new ClienteFormViewModel(existente);
    }

    private ClienteFormViewModel Formulario => (ClienteFormViewModel)DataContext!;

    private void AoSalvar(object? remetente, RoutedEventArgs evento) =>
        Close(Formulario.ParaDados());

    private void AoCancelar(object? remetente, RoutedEventArgs evento) =>
        Close(null);
}
