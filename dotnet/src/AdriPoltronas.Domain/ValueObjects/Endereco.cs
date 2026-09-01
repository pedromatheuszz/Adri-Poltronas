using AdriPoltronas.Domain.Rules;

namespace AdriPoltronas.Domain.ValueObjects;

/// <summary>Onde a poltrona e entregue ou retirada.</summary>
/// <remarks>
/// Agrupar os quatro campos evita a assinatura de sete strings soltas que o
/// backend Python tinha (<c>salvar_cliente(nome, cep, rua, bairro, cidade,
/// ...)</c>), em que trocar rua com bairro na chamada compilava e gravava
/// errado.
/// </remarks>
public sealed record Endereco
{
    // Construtor sem parametros para o ORM materializar o objeto. Os setters
    // sao privados pelo mesmo motivo: de fora, um Endereco so nasce validado.
    private Endereco()
    {
        Rua = string.Empty;
        Bairro = string.Empty;
        Cidade = string.Empty;
    }

    private Endereco(Cep cep, string rua, string bairro, string cidade)
    {
        Cep = cep;
        Rua = rua;
        Bairro = bairro;
        Cidade = cidade;
    }

    public Cep Cep { get; private set; }
    public string Rua { get; private set; }
    public string Bairro { get; private set; }
    public string Cidade { get; private set; }

    /// <summary>
    /// Monta um endereco validado, acumulando os problemas em <paramref name="erros"/>.
    /// </summary>
    /// <returns>null quando algum campo e invalido.</returns>
    public static Endereco? TentarCriar(
        string? cepBruto,
        string? rua,
        string? bairro,
        string? cidade,
        List<string> erros)
    {
        var quantidadeInicial = erros.Count;

        if (!Cep.TentarCriar(cepBruto, out var cep))
        {
            erros.Add("CEP invalido. Use o formato 00000-000.");
        }

        var ruaLimpa = TextoDoCadastro.Normalizar(rua, TextoDoCadastro.EnderecoMaximo);
        TextoDoCadastro.Exigir(ruaLimpa, "Rua", TextoDoCadastro.EnderecoMaximo, erros);

        var bairroLimpo = TextoDoCadastro.Normalizar(bairro, TextoDoCadastro.EnderecoMaximo);
        TextoDoCadastro.Exigir(bairroLimpo, "Bairro", TextoDoCadastro.EnderecoMaximo, erros);

        var cidadeLimpa = TextoDoCadastro.Normalizar(cidade, TextoDoCadastro.CidadeMaxima);
        TextoDoCadastro.Exigir(cidadeLimpa, "Cidade", TextoDoCadastro.CidadeMaxima, erros);

        return erros.Count > quantidadeInicial
            ? null
            : new Endereco(cep, ruaLimpa, bairroLimpo, cidadeLimpa);
    }

    /// <summary>
    /// Reconstroi a partir do banco, sem validar.
    /// </summary>
    /// <remarks>
    /// A base tem registros anteriores a estas regras -- clientes com CEP em
    /// branco, importados antes da validacao existir. Validar na leitura faria
    /// a lista inteira falhar por causa deles.
    /// </remarks>
    public static Endereco Reconstituir(string? cep, string? rua, string? bairro, string? cidade) =>
        new(
            Cep.Reconstituir(cep),
            rua ?? string.Empty,
            bairro ?? string.Empty,
            cidade ?? string.Empty);

    public override string ToString() =>
        string.Join(", ", new[] { Rua, Bairro, Cidade }.Where(p => !string.IsNullOrWhiteSpace(p)));
}
