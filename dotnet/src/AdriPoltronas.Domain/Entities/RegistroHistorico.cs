using AdriPoltronas.Domain.Enums;

namespace AdriPoltronas.Domain.Entities;

/// <summary>
/// Linha do historico de alteracoes de um cliente.
/// </summary>
/// <remarks>
/// Guarda <see cref="ClienteNome"/> em vez de depender do relacionamento
/// porque o registro precisa sobreviver a exclusao do cliente -- a tabela usa
/// ON DELETE SET NULL justamente para isso. Um historico que perde o nome de
/// quem foi excluido nao serve para auditoria nenhuma.
/// </remarks>
public sealed class RegistroHistorico
{
    private RegistroHistorico()
    {
        ClienteNome = string.Empty;
        Detalhes = string.Empty;
    }

    private RegistroHistorico(Cliente? cliente, string clienteNome, AcaoHistorico acao, string detalhes, DateTime quando)
    {
        Cliente = cliente;
        ClienteNome = clienteNome;
        Acao = acao;
        Detalhes = detalhes;
        DataHora = quando;
    }

    public int Id { get; private set; }
    public int? ClienteId { get; private set; }

    /// <summary>
    /// Cliente referenciado, quando ele continua existindo.
    /// </summary>
    /// <remarks>
    /// Guardar a entidade, e nao so o id, e o que permite gravar cadastro e
    /// historico numa unica transacao: no cadastro o id ainda e 0 quando o
    /// registro e criado, e quem preenche a chave estrangeira depois do insert
    /// e o ORM, seguindo esta navegacao.
    /// </remarks>
    public Cliente? Cliente { get; private set; }

    public string ClienteNome { get; private set; }
    public AcaoHistorico Acao { get; private set; }
    public string Detalhes { get; private set; }
    public DateTime DataHora { get; private set; }

    public static RegistroHistorico Criacao(Cliente cliente, DateTime quando) =>
        new(cliente, cliente.Nome, AcaoHistorico.Criacao, "Cliente cadastrado", quando);

    public static RegistroHistorico Atualizacao(
        Cliente cliente, IReadOnlyList<string> mudancas, DateTime quando) =>
        new(
            cliente,
            cliente.Nome,
            AcaoHistorico.Atualizacao,
            mudancas.Count > 0
                ? string.Join("; ", mudancas)
                : "Atualizacao sem alteracoes detectadas",
            quando);

    /// <summary>
    /// Registro de exclusao, sem vinculo com o cliente.
    /// </summary>
    /// <remarks>
    /// Fica com <see cref="ClienteId"/> nulo porque a linha do cliente deixa
    /// de existir na mesma transacao -- e a coluna e declarada
    /// <c>ON DELETE SET NULL</c> exatamente para esse caso. O nome e o endereco
    /// ficam no texto, que e o que a auditoria precisa ler depois.
    /// </remarks>
    public static RegistroHistorico Exclusao(Cliente cliente, DateTime quando) =>
        new(
            null,
            cliente.Nome,
            AcaoHistorico.Exclusao,
            $"Cliente excluido: {cliente.Nome}, {cliente.Endereco.Cidade}, {cliente.Endereco.Bairro}",
            quando);

    public static RegistroHistorico Importacao(Cliente cliente, DateTime quando) =>
        new(cliente, cliente.Nome, AcaoHistorico.Importacao, "Importado em lote", quando);
}
