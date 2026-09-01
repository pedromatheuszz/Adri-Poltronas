using AdriPoltronas.Application.Dtos;
using Avalonia.Controls;
using Avalonia.Interactivity;

namespace AdriPoltronas.Desktop.Views;

/// <summary>
/// Mostra o codigo Pix ou o link do boleto de uma cobranca ja emitida.
/// </summary>
/// <remarks>
/// Exibe o que esta gravado no lancamento; nao emite nada. Este dialogo nao
/// tem ViewModel proprio porque nao ha estado a manter -- e leitura de um DTO.
/// Os dois manipuladores existem porque copiar para a area de transferencia e
/// fechar a janela sao operacoes da janela, sem binding equivalente.
/// </remarks>
public partial class CobrancaDialog : Window
{
    public CobrancaDialog() : this(null)
    {
    }

    public CobrancaDialog(PagamentoDto? pagamento)
    {
        InitializeComponent();
        DataContext = pagamento;
    }

    /// <summary>Copia o texto do campo indicado pelo <c>Tag</c> do botao.</summary>
    /// <remarks>
    /// Um manipulador para os dois botoes: qual texto copiar e dado do XAML, e
    /// nao um metodo por campo.
    /// </remarks>
    private async void AoCopiar(object? remetente, RoutedEventArgs evento)
    {
        if (remetente is not Button { Tag: TextBox campo } ||
            string.IsNullOrWhiteSpace(campo.Text) ||
            Clipboard is null)
        {
            return;
        }

        await Clipboard.SetTextAsync(campo.Text);
    }

    private void AoFechar(object? remetente, RoutedEventArgs evento) => Close();
}
