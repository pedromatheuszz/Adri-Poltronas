using AdriPoltronas.Application.Dtos;
using AdriPoltronas.Desktop.ViewModels;
using Avalonia.Controls;
using Avalonia.Interactivity;

namespace AdriPoltronas.Desktop.Views;

/// <summary>
/// Formulario de lancamento financeiro.
/// </summary>
/// <remarks>
/// Como no formulario de cliente, os dois manipuladores existem apenas porque
/// fechar devolvendo um valor e responsabilidade da janela -- nao ha binding
/// para <c>Close(resultado)</c>. Nenhuma regra passa por aqui.
/// </remarks>
public partial class PagamentoDialog : Window
{
    public PagamentoDialog() : this([])
    {
    }

    public PagamentoDialog(IReadOnlyList<ClienteDto> clientes)
    {
        InitializeComponent();
        DataContext = new PagamentoFormViewModel(clientes);
    }

    private PagamentoFormViewModel Formulario => (PagamentoFormViewModel)DataContext!;

    private void AoSalvar(object? remetente, RoutedEventArgs evento) =>
        Close(Formulario.ParaDados());

    private void AoCancelar(object? remetente, RoutedEventArgs evento) => Close(null);
}
