using AdriPoltronas.Application.Dtos;
using AdriPoltronas.Domain.Enums;
using CommunityToolkit.Mvvm.ComponentModel;

namespace AdriPoltronas.Desktop.ViewModels;

/// <summary>
/// Estado do formulario de cliente.
/// </summary>
/// <remarks>
/// A unica validacao aqui e a de apresentacao: o botao Salvar so habilita com
/// um nome preenchido, para nao enviar uma requisicao obviamente vazia. CEP,
/// tipo e limites de tamanho sao conferidos no Domain e voltam como mensagem
/// -- duplicar essas regras na tela criaria duas fontes de verdade que
/// divergem na primeira mudanca.
/// </remarks>
public sealed partial class ClienteFormViewModel : ObservableObject
{
    public ClienteFormViewModel(ClienteDto? existente)
    {
        EhEdicao = existente is not null;
        _nome = existente?.Nome ?? string.Empty;
        _cep = existente?.Cep ?? string.Empty;
        _rua = existente?.Rua ?? string.Empty;
        _bairro = existente?.Bairro ?? string.Empty;
        _cidade = existente?.Cidade ?? string.Empty;
        _tipo = existente?.Tipo ?? TipoAtendimentoExtensions.TextoEntrega;
        _observacoes = existente?.Observacoes ?? string.Empty;
    }

    public bool EhEdicao { get; }

    public string Titulo => EhEdicao ? "Editar cliente" : "Novo cliente";

    /// <summary>Os dois unicos valores que o dominio aceita.</summary>
    public IReadOnlyList<string> TiposDisponiveis { get; } =
    [
        TipoAtendimentoExtensions.TextoEntrega,
        TipoAtendimentoExtensions.TextoRetirada,
    ];

    [ObservableProperty]
    [NotifyPropertyChangedFor(nameof(PodeSalvar))]
    private string _nome;

    [ObservableProperty]
    private string _cep;

    [ObservableProperty]
    private string _rua;

    [ObservableProperty]
    private string _bairro;

    [ObservableProperty]
    private string _cidade;

    [ObservableProperty]
    private string _tipo;

    [ObservableProperty]
    private string _observacoes;

    public bool PodeSalvar => !string.IsNullOrWhiteSpace(Nome);

    public DadosDoCliente ParaDados() =>
        new(Nome, Cep, Rua, Bairro, Cidade, Tipo, Observacoes);
}
