namespace AdriPoltronas.Application.Dtos;

/// <summary>Endereco devolvido pela consulta de CEP.</summary>
/// <remarks>
/// Campos vazios sao normais: o CEP de uma cidade pequena costuma vir sem rua
/// nem bairro. O formulario preenche o que veio e deixa o resto para o
/// operador.
/// </remarks>
public sealed record EnderecoConsultado(
    string Cep,
    string Rua,
    string Bairro,
    string Cidade,
    string Uf)
{
    public static EnderecoConsultado Vazio { get; } =
        new(string.Empty, string.Empty, string.Empty, string.Empty, string.Empty);

    public bool TemBairro => !string.IsNullOrWhiteSpace(Bairro);
}

/// <summary>Ponto de um cliente no mapa.</summary>
public sealed record PontoNoMapa(
    int ClienteId,
    string Nome,
    string Endereco,
    string Tipo,
    double Latitude,
    double Longitude);
