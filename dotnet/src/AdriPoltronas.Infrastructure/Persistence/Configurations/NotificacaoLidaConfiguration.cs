using AdriPoltronas.Infrastructure.Persistence.Entities;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;

namespace AdriPoltronas.Infrastructure.Persistence.Configurations;

/// <summary>Mapeia as chaves lidas na tabela <c>notificacoes_lidas</c>.</summary>
public sealed class NotificacaoLidaConfiguration : IEntityTypeConfiguration<NotificacaoLida>
{
    public void Configure(EntityTypeBuilder<NotificacaoLida> lida)
    {
        lida.ToTable("notificacoes_lidas");

        // A chave da notificacao e a chave primaria: e ela que precisa ser
        // estavel entre execucoes para o alerta dispensado nao voltar.
        lida.HasKey(l => l.Chave);
        lida.Property(l => l.Chave).HasColumnName("chave").HasMaxLength(120);

        lida.Property(l => l.LidaEm)
            .HasColumnName("lida_em")
            .HasConversion(ConversoresDeData.TextoLocal);
    }
}
