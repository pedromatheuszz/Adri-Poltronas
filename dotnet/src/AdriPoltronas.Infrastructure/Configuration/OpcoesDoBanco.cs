namespace AdriPoltronas.Infrastructure.Configuration;

/// <summary>Qual banco usar e onde ele fica.</summary>
public enum ProvedorDeBanco
{
    Sqlite = 0,
    PostgreSql = 1,
}

/// <summary>
/// Configuracao de persistencia, lida de <c>appsettings.json</c> ou do ambiente.
/// </summary>
/// <remarks>
/// Caminho e provedor ficam aqui, e nao espalhados em constantes: hoje o app e
/// local e usa SQLite; se um dia duas maquinas precisarem da mesma base, muda
/// o provedor e a string de conexao, sem tocar em caso de uso nenhum.
/// </remarks>
public sealed class OpcoesDoBanco
{
    public const string Secao = "Banco";

    public ProvedorDeBanco Provedor { get; init; } = ProvedorDeBanco.Sqlite;

    /// <summary>
    /// String de conexao. Vazia usa o arquivo padrao do usuario.
    /// </summary>
    /// <remarks>
    /// Nunca deve conter senha em texto no arquivo versionado. Para PostgreSQL,
    /// use variavel de ambiente (<c>Banco__ConexaoString</c>).
    /// </remarks>
    public string ConexaoString { get; init; } = string.Empty;

    /// <summary>
    /// Aplica as migracoes do EF Core no arranque.
    /// </summary>
    /// <remarks>
    /// Falso por padrao de proposito. Enquanto o backend Python existir, quem
    /// manda no schema do banco em uso e o Alembic; deixar os dois aplicando
    /// migracao na mesma base e receita para versao inconsistente.
    /// </remarks>
    public bool AplicarMigracoes { get; init; }
}
