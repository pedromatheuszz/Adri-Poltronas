using AdriPoltronas.Domain.Entities;
using AdriPoltronas.Domain.Enums;
using AdriPoltronas.Domain.Rules;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;

namespace AdriPoltronas.Infrastructure.Persistence.Configurations;

/// <summary>Mapeia <see cref="EntregaAgendada"/> na tabela <c>entregas_agendadas</c>.</summary>
public sealed class EntregaAgendadaConfiguration : IEntityTypeConfiguration<EntregaAgendada>
{
    public void Configure(EntityTypeBuilder<EntregaAgendada> entrega)
    {
        entrega.ToTable("entregas_agendadas");
        entrega.HasKey(e => e.Id);
        entrega.Property(e => e.Id).HasColumnName("id").ValueGeneratedOnAdd();

        entrega.Property(e => e.ClienteId).HasColumnName("cliente_id").IsRequired();
        entrega.Property(e => e.ClienteNome)
            .HasColumnName("cliente_nome")
            .HasMaxLength(TextoDoCadastro.NomeMaximo);

        entrega.Property(e => e.DataEntrega)
            .HasColumnName("data_entrega")
            .HasConversion(ConversoresDeValor.DataEmTexto)
            .IsRequired();

        // Hora opcional: ha entregas combinadas so pelo dia.
        entrega.Property(e => e.HoraEntrega).HasColumnName("hora_entrega").HasMaxLength(5);

        entrega.Property(e => e.Descricao)
            .HasColumnName("descricao")
            .HasMaxLength(TextoDoCadastro.ObservacoesMaximas);

        entrega.Property(e => e.Status)
            .HasColumnName("status")
            .HasConversion(
                status => status.ParaTexto(),
                texto => StatusEntregaExtensions.DoTexto(texto))
            .IsRequired();

        entrega.Property(e => e.CriadoEm)
            .HasColumnName("criado_em")
            .HasConversion(ConversoresDeData.TextoLocal);

        // Os alertas leem sempre "pendentes ate tal data": o par status/data e
        // exatamente o filtro, e o indice cobre os dois.
        entrega.HasIndex(e => new { e.Status, e.DataEntrega })
            .HasDatabaseName("ix_entregas_status_data");
    }
}
