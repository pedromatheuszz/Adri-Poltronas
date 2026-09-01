using AdriPoltronas.Application.Dtos;
using AdriPoltronas.Domain.Enums;
using CommunityToolkit.Mvvm.ComponentModel;

namespace AdriPoltronas.Desktop.ViewModels;

/// <summary>
/// Estado do formulario de lancamento financeiro.
/// </summary>
/// <remarks>
/// Como no formulario de cliente, a unica checagem daqui e de apresentacao:
/// habilitar o botao Salvar. Limites de valor, formato de data e coerencia
/// entre status e data de pagamento sao do Domain -- repetir isso na tela
/// criaria duas fontes de verdade que divergem na primeira mudanca.
/// </remarks>
public sealed partial class PagamentoFormViewModel : ObservableObject
{
    public PagamentoFormViewModel(IReadOnlyList<ClienteDto> clientes)
    {
        Clientes = clientes;
        _cliente = clientes.FirstOrDefault();
        _dataVencimento = DateTime.Now.ToString("yyyy-MM-dd");
    }

    public IReadOnlyList<ClienteDto> Clientes { get; }

    public IReadOnlyList<string> TiposDisponiveis { get; } =
    [
        TipoPagamento.Pix.ParaTexto(),
        TipoPagamento.Boleto.ParaTexto(),
        TipoPagamento.Dinheiro.ParaTexto(),
        TipoPagamento.Cartao.ParaTexto(),
        TipoPagamento.Outro.ParaTexto(),
    ];

    public IReadOnlyList<string> StatusDisponiveis { get; } =
    [
        StatusPagamento.Pendente.ParaTexto(),
        StatusPagamento.Recebido.ParaTexto(),
    ];

    [ObservableProperty]
    [NotifyPropertyChangedFor(nameof(PodeSalvar))]
    private ClienteDto? _cliente;

    [ObservableProperty]
    [NotifyPropertyChangedFor(nameof(PodeSalvar))]
    private string _valor = string.Empty;

    [ObservableProperty]
    private string _descricao = string.Empty;

    [ObservableProperty]
    private string _dataVencimento;

    [ObservableProperty]
    private string _tipo = TipoPagamento.Pix.ParaTexto();

    [ObservableProperty]
    private string _status = StatusPagamento.Pendente.ParaTexto();

    public bool PodeSalvar => Cliente is not null && QuantiaDigitada() > 0m;

    public DadosDoPagamento ParaDados() => new(
        Cliente?.Id ?? 0,
        Cliente?.Nome,
        QuantiaDigitada(),
        Descricao,
        DataVencimento,
        Tipo,
        Status,
        null);

    /// <summary>
    /// Le o valor digitado, aceitando virgula decimal.
    /// </summary>
    /// <remarks>
    /// Um metodo so, usado pela habilitacao do botao e pelo envio. Duas
    /// leituras separadas divergiriam, e a divergencia apareceria como botao
    /// habilitado que grava zero.
    /// </remarks>
    private decimal QuantiaDigitada() =>
        decimal.TryParse(
            Valor.Replace(',', '.'),
            System.Globalization.NumberStyles.Number,
            System.Globalization.CultureInfo.InvariantCulture,
            out var quantia) ? quantia : 0m;
}
