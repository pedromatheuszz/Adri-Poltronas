using AdriPoltronas.Application.Dtos;

namespace AdriPoltronas.Desktop.Navigation;

/// <summary>
/// Janelas modais pedidas pelos ViewModels.
/// </summary>
/// <remarks>
/// A interface fica no Desktop porque dialogo e assunto de interface -- a
/// Application nao deve saber que existe janela. O ViewModel depende desta
/// abstracao, e nao de <c>Window</c>, para continuar testavel sem UI.
/// </remarks>
public interface IDialogos
{
    /// <summary>Abre o formulario de cliente. Devolve null se o operador cancelar.</summary>
    Task<DadosDoCliente?> EditarClienteAsync(ClienteDto? existente);

    /// <summary>
    /// Abre o formulario de lancamento financeiro.
    /// </summary>
    /// <param name="clientes">
    /// Lista para escolher o dono da cobranca. Vem de quem chama, e nao de uma
    /// consulta interna: o dialogo nao deve alcancar caso de uso nenhum.
    /// </param>
    Task<DadosDoPagamento?> NovoPagamentoAsync(IReadOnlyList<ClienteDto> clientes);

    /// <summary>Exibe o codigo Pix ou o link do boleto de uma cobranca emitida.</summary>
    Task MostrarCobrancaAsync(PagamentoDto pagamento);

    Task<bool> ConfirmarAsync(string titulo, string pergunta);

    /// <summary>Caminho escolhido para gravar, ou null se cancelado.</summary>
    Task<string?> EscolherArquivoParaSalvarAsync(
        string titulo, string nomeSugerido, FormatoDeArquivo formato);

    /// <summary>Caminho escolhido para ler, ou null se cancelado.</summary>
    Task<string?> EscolherArquivoParaAbrirAsync(string titulo);
}
