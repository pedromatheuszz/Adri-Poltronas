using AdriPoltronas.Infrastructure.Sistema;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Design;

namespace AdriPoltronas.Infrastructure.Persistence;

/// <summary>
/// Constroi o contexto para as ferramentas de linha de comando do EF Core.
/// </summary>
/// <remarks>
/// O <c>dotnet ef</c> precisa instanciar o <see cref="AdriPoltronasDbContext"/>
/// sem subir a aplicacao. Sem esta fabrica ele tentaria achar um host web --
/// que nao existe num aplicativo de desktop -- e falharia ao gerar migracao.
///
/// So e usada em tempo de projeto: em execucao, quem monta o contexto e o
/// registro de dependencias, com as opcoes vindas da configuracao.
/// </remarks>
public sealed class FabricaDeContextoEmTempoDeProjeto
    : IDesignTimeDbContextFactory<AdriPoltronasDbContext>
{
    public AdriPoltronasDbContext CreateDbContext(string[] argumentos)
    {
        var opcoes = new DbContextOptionsBuilder<AdriPoltronasDbContext>()
            .UseSqlite($"Data Source={PastaDeDados.CaminhoDoBanco()}")
            .Options;

        return new AdriPoltronasDbContext(opcoes);
    }
}
