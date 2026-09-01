using AdriPoltronas.Domain.Enums;
using AdriPoltronas.Domain.Exceptions;
using AdriPoltronas.Domain.Rules;
using AdriPoltronas.Domain.ValueObjects;

namespace AdriPoltronas.Domain.Entities;

/// <summary>
/// Cliente da Adri Poltronas: quem compra e para onde a poltrona vai.
/// </summary>
/// <remarks>
/// As propriedades tem setter privado de proposito. Toda mudanca passa por
/// <see cref="Atualizar"/>, que valida e move <see cref="AtualizadoEm"/> --
/// no modelo anterior o UPDATE era montado a mao em cada chamada e nada
/// impedia gravar um cliente sem nome.
/// </remarks>
public sealed class Cliente
{
    // Construtor sem parametros para o Entity Framework materializar a
    // entidade. Privado para que nenhum outro caminho o alcance.
    private Cliente()
    {
        Nome = string.Empty;
        Endereco = Endereco.Reconstituir(null, null, null, null);
        Observacoes = string.Empty;
    }

    private Cliente(string nome, Endereco endereco, TipoAtendimento tipo, string observacoes, DateTime agora)
    {
        Nome = nome;
        Endereco = endereco;
        Tipo = tipo;
        Observacoes = observacoes;
        CriadoEm = agora;
        AtualizadoEm = agora;
    }

    public int Id { get; private set; }
    public string Nome { get; private set; }
    public Endereco Endereco { get; private set; }
    public TipoAtendimento Tipo { get; private set; }
    public string Observacoes { get; private set; }
    public DateTime CriadoEm { get; private set; }
    public DateTime AtualizadoEm { get; private set; }

    /// <summary>Cria um cliente valido ou lanca <see cref="ValidacaoException"/>.</summary>
    public static Cliente Criar(
        string? nome,
        string? cep,
        string? rua,
        string? bairro,
        string? cidade,
        string? tipo,
        string? observacoes,
        DateTime agora)
    {
        var erros = new List<string>();
        var dados = Conferir(nome, cep, rua, bairro, cidade, tipo, observacoes, erros);

        if (erros.Count > 0)
        {
            throw new ValidacaoException(erros);
        }

        return new Cliente(dados.Nome, dados.Endereco!, dados.Tipo, dados.Observacoes, agora);
    }

    /// <summary>Aplica novos dados e devolve a descricao do que mudou.</summary>
    /// <remarks>
    /// A descricao alimenta o historico. Calcular aqui -- e nao no repositorio
    /// -- e o que garante que a comparacao veja os valores ja normalizados:
    /// comparando o texto cru, um espaco a mais digitado no fim do nome
    /// aparecia como alteracao.
    /// </remarks>
    public IReadOnlyList<string> Atualizar(
        string? nome,
        string? cep,
        string? rua,
        string? bairro,
        string? cidade,
        string? tipo,
        string? observacoes,
        DateTime agora)
    {
        var erros = new List<string>();
        var dados = Conferir(nome, cep, rua, bairro, cidade, tipo, observacoes, erros);

        if (erros.Count > 0)
        {
            throw new ValidacaoException(erros);
        }

        var mudancas = new List<string>();
        Comparar("Nome", Nome, dados.Nome, mudancas);
        Comparar("CEP", Endereco.Cep.Valor, dados.Endereco!.Cep.Valor, mudancas);
        Comparar("Rua", Endereco.Rua, dados.Endereco.Rua, mudancas);
        Comparar("Bairro", Endereco.Bairro, dados.Endereco.Bairro, mudancas);
        Comparar("Cidade", Endereco.Cidade, dados.Endereco.Cidade, mudancas);
        Comparar("Tipo", Tipo.ParaTexto(), dados.Tipo.ParaTexto(), mudancas);
        Comparar("Obs", Observacoes, dados.Observacoes, mudancas);

        Nome = dados.Nome;
        Endereco = dados.Endereco;
        Tipo = dados.Tipo;
        Observacoes = dados.Observacoes;
        AtualizadoEm = agora;

        return mudancas;
    }

    private static void Comparar(string rotulo, string anterior, string novo, List<string> mudancas)
    {
        if (!string.Equals(anterior, novo, StringComparison.Ordinal))
        {
            mudancas.Add($"{rotulo}: '{anterior}' -> '{novo}'");
        }
    }

    private static (string Nome, Endereco? Endereco, TipoAtendimento Tipo, string Observacoes) Conferir(
        string? nome,
        string? cep,
        string? rua,
        string? bairro,
        string? cidade,
        string? tipo,
        string? observacoes,
        List<string> erros)
    {
        var nomeLimpo = TextoDoCadastro.Normalizar(nome, TextoDoCadastro.NomeMaximo);
        TextoDoCadastro.Exigir(
            nomeLimpo, "Nome", TextoDoCadastro.NomeMaximo, erros, TextoDoCadastro.NomeMinimo);

        var endereco = Endereco.TentarCriar(cep, rua, bairro, cidade, erros);

        if (!TipoAtendimentoExtensions.TentarConverter(tipo, out var tipoConvertido))
        {
            erros.Add("Entrega/Retirada invalido. Escolha 'Entrega' ou 'Retirada'.");
        }

        // Observacoes e livre: so o tamanho e limitado.
        var observacoesLimpas =
            TextoDoCadastro.Normalizar(observacoes, TextoDoCadastro.ObservacoesMaximas);

        return (nomeLimpo, endereco, tipoConvertido, observacoesLimpas);
    }
}
