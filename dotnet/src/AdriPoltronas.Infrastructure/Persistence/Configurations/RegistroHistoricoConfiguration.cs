using AdriPoltronas.Domain.Entities;
using AdriPoltronas.Domain.Enums;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;

namespace AdriPoltronas.Infrastructure.Persistence.Configurations;

/// <summary>Mapeia <see cref="RegistroHistorico"/> na tabela <c>historico</c>.</summary>
public sealed class RegistroHistoricoConfiguration : IEntityTypeConfiguration<RegistroHistorico>
{
    public void Configure(EntityTypeBuilder<RegistroHistorico> registro)
    {
        registro.ToTable("historico");
        registro.HasKey(r => r.Id);
        registro.Property(r => r.Id).HasColumnName("id").ValueGeneratedOnAdd();

        registro.Property(r => r.ClienteId).HasColumnName("cliente_id");
        registro.Property(r => r.ClienteNome).HasColumnName("cliente_nome");
        registro.Property(r => r.Detalhes).HasColumnName("detalhes");

        registro.Property(r => r.Acao)
            .HasColumnName("acao")
            // CRIACAO, ATUALIZACAO... e o que os 40 registros existentes usam.
            .HasConversion(
                acao => acao.ParaTexto(),
                texto => AcaoHistoricoExtensions.DoTexto(texto))
            .IsRequired();

        registro.Property(r => r.DataHora)
            .HasColumnName("data_hora")
            .HasConversion(ConversoresDeData.TextoLocal);

        // A navegacao existe para o ORM preencher cliente_id depois do insert
        // do cliente, o que permite gravar cadastro e historico numa transacao
        // so. DeleteBehavior.SetNull espelha o ON DELETE SET NULL do schema:
        // excluir um cliente nao apaga a auditoria dele.
        registro.HasOne(r => r.Cliente)
            .WithMany()
            .HasForeignKey(r => r.ClienteId)
            .OnDelete(DeleteBehavior.SetNull);

        // A tela de auditoria le sempre os mais recentes primeiro.
        registro.HasIndex(r => r.DataHora);
    }
}
