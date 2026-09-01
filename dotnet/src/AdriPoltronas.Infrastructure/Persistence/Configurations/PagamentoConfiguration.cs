using AdriPoltronas.Domain.Entities;
using AdriPoltronas.Domain.Enums;
using AdriPoltronas.Domain.Rules;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;

namespace AdriPoltronas.Infrastructure.Persistence.Configurations;

/// <summary>Mapeia <see cref="Pagamento"/> na tabela <c>pagamentos</c> existente.</summary>
public sealed class PagamentoConfiguration : IEntityTypeConfiguration<Pagamento>
{
    public void Configure(EntityTypeBuilder<Pagamento> pagamento)
    {
        pagamento.ToTable("pagamentos");
        pagamento.HasKey(p => p.Id);
        pagamento.Property(p => p.Id).HasColumnName("id").ValueGeneratedOnAdd();

        pagamento.Property(p => p.ClienteId).HasColumnName("cliente_id").IsRequired();

        // O nome do cliente e copiado para a linha, e nao lido por join. Assim
        // a cobranca continua identificavel depois que o cadastro e excluido --
        // que e justamente quando alguem precisa saber de quem era a divida.
        pagamento.Property(p => p.ClienteNome)
            .HasColumnName("cliente_nome")
            .HasMaxLength(TextoDoCadastro.NomeMaximo);

        pagamento.Property(p => p.Valor)
            .HasColumnName("valor")
            .HasConversion(ConversoresDeValor.Reais)
            .IsRequired();

        pagamento.Property(p => p.Descricao)
            .HasColumnName("descricao")
            .HasMaxLength(TextoDoCadastro.ObservacoesMaximas);

        pagamento.Property(p => p.Status)
            .HasColumnName("status")
            .HasConversion(
                status => status.ParaTexto(),
                texto => StatusPagamentoExtensions.DoTexto(texto))
            .IsRequired();

        pagamento.Property(p => p.Tipo)
            .HasColumnName("tipo_pagamento")
            .HasConversion(
                tipo => tipo.ParaTexto(),
                texto => TipoPagamentoExtensions.DoTexto(texto))
            .IsRequired();

        pagamento.Property(p => p.DataPagamento)
            .HasColumnName("data_pagamento")
            .HasConversion(ConversoresDeValor.DataEmTexto);
        pagamento.Property(p => p.DataVencimento)
            .HasColumnName("data_vencimento")
            .HasConversion(ConversoresDeValor.DataEmTexto);

        pagamento.Property(p => p.CriadoEm)
            .HasColumnName("criado_em")
            .HasConversion(ConversoresDeData.TextoLocal);

        // Os artefatos da cobranca online moram nas mesmas cinco colunas que o
        // schema ja tem; sao um value object so para nao inchar a entidade.
        pagamento.OwnsOne(p => p.Cobranca, cobranca =>
        {
            cobranca.Property(c => c.AsaasPaymentId).HasColumnName("asaas_payment_id");
            cobranca.Property(c => c.PixPayload).HasColumnName("pix_payload");
            cobranca.Property(c => c.PixQrCode).HasColumnName("pix_qr_code");
            cobranca.Property(c => c.BoletoUrl).HasColumnName("boleto_url");
            cobranca.Property(c => c.NossoNumero).HasColumnName("nosso_numero");
        });
        pagamento.Navigation(p => p.Cobranca).IsRequired();

        // A lista de cobrancas de um cliente e a consulta mais frequente da
        // aba financeira, e esta e uma igualdade -- indice comum resolve.
        pagamento.HasIndex(p => p.ClienteId).HasDatabaseName("ix_pagamentos_cliente");
    }
}
