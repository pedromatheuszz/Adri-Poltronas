using AdriPoltronas.Domain.Entities;
using AdriPoltronas.Domain.Enums;

namespace AdriPoltronas.Application.Dtos;

/// <summary>Cobranca como a tela a exibe.</summary>
public sealed record PagamentoDto(
    int Id,
    int ClienteId,
    string ClienteNome,
    decimal Valor,
    string ValorFormatado,
    string Descricao,
    string Status,
    string Tipo,
    string DataVencimento,
    string DataPagamento,
    bool EmAtraso,
    bool CobrancaEmitida,
    string PixPayload,
    string PixQrCode,
    string BoletoUrl)
{
    /// <summary>Data que a lista mostra: recebimento quando houve, senao vencimento.</summary>
    public string DataExibida =>
        string.IsNullOrEmpty(DataPagamento) ? DataVencimento : DataPagamento;

    public static PagamentoDto De(Pagamento pagamento, DateTime agora) => new(
        pagamento.Id,
        pagamento.ClienteId,
        pagamento.ClienteNome,
        pagamento.Valor.Valor,
        pagamento.Valor.Formatado(),
        pagamento.Descricao,
        pagamento.Status.ParaTexto(),
        pagamento.Tipo.ParaTexto(),
        pagamento.DataVencimento.Formatada(),
        pagamento.DataPagamento.Formatada(),
        pagamento.EstaEmAtraso(agora),
        pagamento.Cobranca.Emitida,
        pagamento.Cobranca.PixPayload,
        pagamento.Cobranca.PixQrCode,
        pagamento.Cobranca.BoletoUrl);
}

/// <summary>O que o formulario de recebimento envia.</summary>
public sealed record DadosDoPagamento(
    int ClienteId,
    string? ClienteNome,
    decimal Valor,
    string? Descricao,
    string? DataVencimento,
    string? Tipo,
    string? Status,
    string? DataPagamento);

/// <summary>Totais por situacao, exibidos abaixo da lista.</summary>
public sealed record MetricasPagamentosDto(
    decimal TotalRecebido,
    decimal TotalPendente,
    decimal TotalAtrasado,
    int QuantidadeRecebida,
    int QuantidadePendente)
{
    public static MetricasPagamentosDto Vazio => new(0, 0, 0, 0, 0);
}

/// <summary>Filtro da tela de pagamentos.</summary>
public sealed record FiltroDePagamentos(string? Cliente = null, string? Status = null);
