using AdriPoltronas.Infrastructure.Configuration;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;

namespace AdriPoltronas.Infrastructure.Persistence;

/// <summary>
/// Prepara o banco no arranque, sem atropelar o schema que ja existe.
/// </summary>
/// <remarks>
/// Enquanto o backend Python estiver em uso, quem versiona o schema e o
/// Alembic. Se o EF Core tambem aplicasse migracoes na mesma base, as duas
/// ferramentas passariam a disputar o controle das tabelas e a primeira
/// migracao do EF tentaria criar <c>clientes</c> por cima da que ja tem quatro
/// cadastros.
///
/// Por isso a deteccao: existindo <c>alembic_version</c>, o schema tem dono e
/// o EF apenas se conecta. A migracao do EF fica para a base nova (instalacao
/// limpa ou PostgreSQL), onde nao ha Alembic nenhum.
/// </remarks>
public sealed class InicializadorDoBanco(
    AdriPoltronasDbContext contexto,
    IOptions<OpcoesDoBanco> opcoes,
    ILogger<InicializadorDoBanco> log)
{
    public async Task PrepararAsync(CancellationToken cancelamento = default)
    {
        if (await SchemaPertenceAoAlembicAsync(cancelamento))
        {
            log.LogInformation(
                "Schema versionado pelo Alembic (backend Python); migracoes do EF Core ignoradas.");
            return;
        }

        if (!opcoes.Value.AplicarMigracoes)
        {
            // Base nova sem migracao habilitada: cria o schema a partir do
            // modelo. Suficiente para uso local e para os testes.
            await contexto.Database.EnsureCreatedAsync(cancelamento);
            return;
        }

        log.LogInformation("Aplicando migracoes do EF Core.");
        await contexto.Database.MigrateAsync(cancelamento);
    }

    private async Task<bool> SchemaPertenceAoAlembicAsync(CancellationToken cancelamento)
    {
        if (!await contexto.Database.CanConnectAsync(cancelamento))
        {
            return false;
        }

        try
        {
            var conexao = contexto.Database.GetDbConnection();
            await contexto.Database.OpenConnectionAsync(cancelamento);
            await using var comando = conexao.CreateCommand();
            // Consulta constante, sem entrada do usuario.
            comando.CommandText =
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='alembic_version'";
            var achou = Convert.ToInt64(await comando.ExecuteScalarAsync(cancelamento)) > 0;
            return achou;
        }
        catch (Exception erro)
        {
            // Um provedor diferente de SQLite nao tem sqlite_master. Nesse caso
            // nao ha Alembic envolvido e o caminho normal de migracao vale.
            log.LogDebug(erro, "Nao foi possivel inspecionar sqlite_master; seguindo sem Alembic.");
            return false;
        }
        finally
        {
            await contexto.Database.CloseConnectionAsync();
        }
    }
}
