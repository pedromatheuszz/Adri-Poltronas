namespace AdriPoltronas.Application.Dtos;

/// <summary>
/// O que o formulario envia para criar ou atualizar um cliente.
/// </summary>
/// <remarks>
/// Todos os campos sao <c>string?</c> porque e exatamente isso que uma caixa
/// de texto produz. A conversao e a validacao acontecem no Domain, em um lugar
/// so -- nao espalhadas pelo ViewModel.
/// </remarks>
public sealed record DadosDoCliente(
    string? Nome,
    string? Cep,
    string? Rua,
    string? Bairro,
    string? Cidade,
    string? Tipo,
    string? Observacoes);
