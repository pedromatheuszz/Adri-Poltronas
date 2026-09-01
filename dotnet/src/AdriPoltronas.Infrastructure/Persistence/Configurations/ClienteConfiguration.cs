using AdriPoltronas.Domain.Entities;
using AdriPoltronas.Domain.Enums;
using AdriPoltronas.Domain.Rules;
using AdriPoltronas.Domain.ValueObjects;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;

namespace AdriPoltronas.Infrastructure.Persistence.Configurations;

/// <summary>Mapeia <see cref="Cliente"/> na tabela <c>clientes</c> existente.</summary>
public sealed class ClienteConfiguration : IEntityTypeConfiguration<Cliente>
{
    public void Configure(EntityTypeBuilder<Cliente> cliente)
    {
        cliente.ToTable("clientes");
        cliente.HasKey(c => c.Id);
        cliente.Property(c => c.Id).HasColumnName("id").ValueGeneratedOnAdd();

        cliente.Property(c => c.Nome)
            .HasColumnName("nome")
            .HasMaxLength(TextoDoCadastro.NomeMaximo)
            .IsRequired();

        // Endereco e value object: mora na mesma tabela, em quatro colunas.
        cliente.OwnsOne(c => c.Endereco, endereco =>
        {
            endereco.Property(e => e.Cep)
                .HasColumnName("cep")
                // O CEP e um tipo do dominio; no banco continua sendo o texto
                // "00000-000" que o schema atual ja guarda.
                .HasConversion(valor => valor.Valor, texto => Cep.Reconstituir(texto));

            endereco.Property(e => e.Rua)
                .HasColumnName("rua")
                .HasMaxLength(TextoDoCadastro.EnderecoMaximo);
            endereco.Property(e => e.Bairro)
                .HasColumnName("bairro")
                .HasMaxLength(TextoDoCadastro.EnderecoMaximo);
            endereco.Property(e => e.Cidade)
                .HasColumnName("cidade")
                .HasMaxLength(TextoDoCadastro.CidadeMaxima);
        });
        cliente.Navigation(c => c.Endereco).IsRequired();

        cliente.Property(c => c.Tipo)
            .HasColumnName("entrega_retirada")
            // Texto, e nao inteiro: e o que a coluna ja contem, e o backend
            // Python compara com a string 'Entrega' nas metricas.
            .HasConversion(
                tipo => tipo.ParaTexto(),
                texto => texto == TipoAtendimentoExtensions.TextoRetirada
                    ? TipoAtendimento.Retirada
                    : TipoAtendimento.Entrega)
            .IsRequired();

        cliente.Property(c => c.Observacoes)
            .HasColumnName("observacoes")
            .HasMaxLength(TextoDoCadastro.ObservacoesMaximas);

        cliente.Property(c => c.CriadoEm)
            .HasColumnName("criado_em")
            .HasConversion(ConversoresDeData.TextoLocal);
        cliente.Property(c => c.AtualizadoEm)
            .HasColumnName("atualizado_em")
            .HasConversion(ConversoresDeData.TextoLocal);

        // Sem indice para a busca, de proposito: o filtro da tela e um
        // "contem" (LIKE '%termo%'), que nenhum indice B-tree atende. Com o
        // volume atual a varredura e imperceptivel; se um dia deixar de ser, a
        // resposta e FTS5 no SQLite ou trigramas no PostgreSQL, nao um indice
        // comum que so ocuparia espaco.
    }
}
