using AdriPoltronas.Domain.Entities;
using AdriPoltronas.Domain.Enums;
using AdriPoltronas.Domain.Exceptions;
using Xunit;

namespace AdriPoltronas.Domain.Tests;

/// <summary>
/// A invariante desta entidade e a coerencia entre status e data de
/// recebimento, porque e ela que o faturamento le.
/// </summary>
public sealed class PagamentoTests
{
    private static readonly DateTime Agora = new(2026, 8, 28, 10, 0, 0);

    private static Pagamento Criar(
        decimal valor = 150m,
        string? vencimento = "2026-09-10",
        string? tipo = "Pix",
        string? status = "Pendente",
        string? dataPagamento = null) =>
        Pagamento.Criar(1, "Cliente", valor, "Poltrona", vencimento, tipo, status,
            dataPagamento, Agora);

    [Fact]
    public void RecebidoSemDataAssumeHoje()
    {
        var pagamento = Criar(status: "Recebido");

        Assert.Equal("2026-08-28", pagamento.DataPagamento.Texto);
    }

    [Fact]
    public void PendenteComDataDePagamentoZeraAData()
    {
        // Uma data em cobranca nao recebida contaria receita que nao entrou.
        var pagamento = Criar(status: "Pendente", dataPagamento: "2026-08-01");

        Assert.False(pagamento.DataPagamento.Preenchida);
    }

    [Fact]
    public void ConfirmarFixaAData()
    {
        var pagamento = Criar();

        pagamento.Confirmar(Agora, "2026-08-20");

        Assert.Equal(StatusPagamento.Recebido, pagamento.Status);
        Assert.Equal("2026-08-20", pagamento.DataPagamento.Texto);
    }

    [Fact]
    public void CancelarRecebidoEProibido()
    {
        var pagamento = Criar(status: "Recebido");

        var erro = Assert.Throws<DomainException>(pagamento.Cancelar);

        Assert.Contains("estorno", erro.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void ConfirmarCanceladoEProibido()
    {
        var pagamento = Criar();
        pagamento.Cancelar();

        Assert.Throws<DomainException>(() => pagamento.Confirmar(Agora));
    }

    [Fact]
    public void ValorForaDosLimitesERecusado()
    {
        var erro = Assert.Throws<ValidacaoException>(() => Criar(valor: 0m));

        Assert.NotEmpty(erro.Erros);
    }

    [Fact]
    public void DataDeVencimentoImpossivelERecusada()
    {
        // O regex sozinho aceitava 2026-13-45, e o SQLite devolvia NULL calado.
        Assert.Throws<ValidacaoException>(() => Criar(vencimento: "2026-13-45"));
    }

    [Fact]
    public void SemDataDePagamentoAReceitaCaiNaDataDeCriacao()
    {
        // Espelha COALESCE(NULLIF(data_pagamento,''), criado_em) do backend.
        var pagamento = Criar();

        Assert.Equal(Agora.Date, pagamento.DataQueContaComoReceita());
    }

    [Fact]
    public void VencidaEPendenteEstaEmAtraso()
    {
        var pagamento = Criar(vencimento: "2026-08-01");

        Assert.True(pagamento.EstaEmAtraso(Agora));
    }

    [Fact]
    public void RecebidaNuncaEstaEmAtraso()
    {
        var pagamento = Criar(vencimento: "2026-08-01", status: "Recebido");

        Assert.False(pagamento.EstaEmAtraso(Agora));
    }

    [Fact]
    public void SomentePixEBoletoGeramCobrancaOnline()
    {
        Assert.True(TipoPagamento.Pix.EmitidoPeloAsaas());
        Assert.True(TipoPagamento.Boleto.EmitidoPeloAsaas());
        Assert.False(TipoPagamento.Dinheiro.EmitidoPeloAsaas());
    }
}
