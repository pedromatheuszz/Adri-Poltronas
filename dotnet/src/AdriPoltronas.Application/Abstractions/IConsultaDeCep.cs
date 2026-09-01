using AdriPoltronas.Application.Dtos;

namespace AdriPoltronas.Application.Abstractions;

/// <summary>Consulta de endereco por CEP.</summary>
public interface IConsultaDeCep
{
    /// <summary>Endereco do CEP, ou nulo quando nao existe ou o servico esta fora.</summary>
    Task<EnderecoConsultado?> ConsultarAsync(string cep, CancellationToken cancelamento = default);
}

/// <summary>
/// Palpite de bairro quando o CEP nao traz um.
/// </summary>
/// <remarks>
/// E o botao de sugestao ao lado do campo. Palpite, nao verdade: o formulario
/// preenche mas deixa editavel, e a ausencia do servico apenas desabilita o
/// botao. O cadastro continua funcionando sem ele.
/// </remarks>
public interface ISugestaoDeBairro
{
    bool Configurado { get; }

    Task<string?> SugerirAsync(
        string cep, string rua, string cidade, CancellationToken cancelamento = default);
}
