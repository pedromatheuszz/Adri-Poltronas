using AdriPoltronas.Domain.Entities;
using AdriPoltronas.Infrastructure.Persistence.Entities;
using Microsoft.EntityFrameworkCore;

namespace AdriPoltronas.Infrastructure.Persistence;

/// <summary>
/// Contexto do Entity Framework sobre o banco da Adri Poltronas.
/// </summary>
/// <remarks>
/// Sem regra de negocio aqui: nenhum <c>SaveChanges</c> sobrescrito que decida
/// o que gravar, nenhum calculo. O contexto so mapeia; quem decide e o Domain,
/// e quem orquestra e a Application.
///
/// O mapeamento aponta para as tabelas que ja existem
/// (<c>clientes</c>, <c>historico</c>, <c>pagamentos</c>, <c>entregas_agendadas</c>,
/// <c>notificacoes_lidas</c>), com os nomes de coluna em snake_case do schema
/// atual: enquanto o backend Python roda sobre a mesma base, as duas pilhas
/// precisam enxergar exatamente as mesmas colunas.
/// </remarks>
public sealed class AdriPoltronasDbContext(DbContextOptions<AdriPoltronasDbContext> opcoes)
    : DbContext(opcoes)
{
    public DbSet<Cliente> Clientes => Set<Cliente>();
    public DbSet<RegistroHistorico> Historico => Set<RegistroHistorico>();
    public DbSet<Pagamento> Pagamentos => Set<Pagamento>();
    public DbSet<EntregaAgendada> Entregas => Set<EntregaAgendada>();
    public DbSet<NotificacaoLida> NotificacoesLidas => Set<NotificacaoLida>();

    protected override void OnModelCreating(ModelBuilder construtor)
    {
        // Uma classe de configuracao por agregado, em Configurations/.
        construtor.ApplyConfigurationsFromAssembly(typeof(AdriPoltronasDbContext).Assembly);
        base.OnModelCreating(construtor);
    }
}
