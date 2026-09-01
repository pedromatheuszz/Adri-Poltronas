using AdriPoltronas.Domain.Enums;
using AdriPoltronas.Domain.Exceptions;
using AdriPoltronas.Domain.Rules;
using AdriPoltronas.Domain.ValueObjects;

namespace AdriPoltronas.Domain.Entities;

/// <summary>
/// Cobranca de um cliente.
/// </summary>
/// <remarks>
/// A invariante que esta entidade existe para proteger e a coerencia entre
/// <see cref="Status"/> e <see cref="DataPagamento"/>. As consultas financeiras
/// leem a data sem cruzar com o status, entao dois estados incoerentes
/// falseiam o faturamento: um "Recebido" sem data fica fora de todo mes da
/// serie, e uma data em cobranca nao recebida conta receita que nao entrou.
///
/// Por isso a data nunca e atribuida diretamente -- ela e derivada do status
/// em <see cref="AjustarDataDeRecebimento"/>, num lugar so.
/// </remarks>
public sealed class Pagamento
{
    private Pagamento()
    {
        ClienteNome = string.Empty;
        Descricao = string.Empty;
        Cobranca = DadosDaCobranca.Nenhuma;
    }

    private Pagamento(
        int clienteId,
        string clienteNome,
        Dinheiro valor,
        string descricao,
        DataSimples vencimento,
        TipoPagamento tipo,
        StatusPagamento status,
        DataSimples dataPagamento,
        DateTime agora)
    {
        ClienteId = clienteId;
        ClienteNome = clienteNome;
        Valor = valor;
        Descricao = descricao;
        DataVencimento = vencimento;
        Tipo = tipo;
        Status = status;
        DataPagamento = dataPagamento;
        CriadoEm = agora;
        Cobranca = DadosDaCobranca.Nenhuma;
    }

    public int Id { get; private set; }
    public int ClienteId { get; private set; }
    public string ClienteNome { get; private set; }
    public Dinheiro Valor { get; private set; }
    public string Descricao { get; private set; }
    public DataSimples DataVencimento { get; private set; }
    public DataSimples DataPagamento { get; private set; }
    public TipoPagamento Tipo { get; private set; }
    public StatusPagamento Status { get; private set; }
    public DateTime CriadoEm { get; private set; }

    /// <summary>Identificadores e artefatos devolvidos pelo Asaas.</summary>
    public DadosDaCobranca Cobranca { get; private set; }

    /// <summary>
    /// Data que conta como receita.
    /// </summary>
    /// <remarks>
    /// Espelha <c>COALESCE(NULLIF(data_pagamento,''), criado_em)</c>, que e como
    /// o backend Python soma o faturamento por mes. Cobranca antiga marcada
    /// como recebida sem data cai na data de criacao, e nao some da serie.
    /// </remarks>
    public DateTime DataQueContaComoReceita() =>
        DataPagamento.ComoDateTime() ?? CriadoEm.Date;

    /// <summary>Vencida e ainda nao paga.</summary>
    public bool EstaEmAtraso(DateTime agora)
    {
        if (Status is StatusPagamento.Recebido or StatusPagamento.Cancelado)
        {
            return false;
        }

        var dias = DataVencimento.DiasAte(agora);
        return dias is < 0;
    }

    public static Pagamento Criar(
        int clienteId,
        string? clienteNome,
        decimal valor,
        string? descricao,
        string? dataVencimento,
        string? tipo,
        string? status,
        string? dataPagamento,
        DateTime agora)
    {
        var erros = new List<string>();

        if (clienteId <= 0)
        {
            erros.Add("Cliente invalido.");
        }

        if (!Dinheiro.TentarCriar(valor, out var quantia))
        {
            erros.Add(
                $"Valor invalido. Use entre {Dinheiro.Minimo:F2} e {Dinheiro.Maximo:F2}.");
        }

        if (!DataSimples.TentarCriar(dataVencimento, out var vencimento))
        {
            erros.Add(string.IsNullOrWhiteSpace(dataVencimento)
                ? "Data de vencimento obrigatoria."
                : "Data de vencimento invalida. Use formato AAAA-MM-DD.");
        }

        if (!TipoPagamentoExtensions.TentarConverter(tipo, out var tipoConvertido))
        {
            erros.Add("Tipo de pagamento invalido.");
        }

        var statusInformado = status?.Trim() ?? string.Empty;
        var statusConvertido = StatusPagamento.Pendente;
        if (statusInformado.Length > 0 &&
            !StatusPagamentoExtensions.TentarConverter(statusInformado, out statusConvertido))
        {
            erros.Add("Status invalido.");
        }

        var pagamentoInformado = dataPagamento?.Trim() ?? string.Empty;
        if (pagamentoInformado.Length > 0 &&
            !DataSimples.TentarCriar(pagamentoInformado, out _))
        {
            erros.Add("Data de pagamento invalida. Use formato AAAA-MM-DD.");
        }

        if (erros.Count > 0)
        {
            throw new ValidacaoException(erros);
        }

        var nome = TextoDoCadastro.Normalizar(clienteNome, TextoDoCadastro.NomeMaximo);
        var texto = TextoDoCadastro.Normalizar(descricao, TextoDoCadastro.ObservacoesMaximas);
        var quitacao = AjustarDataDeRecebimento(statusConvertido, pagamentoInformado, agora);

        return new Pagamento(
            clienteId, nome, quantia, texto, vencimento,
            tipoConvertido, statusConvertido, quitacao, agora);
    }

    /// <summary>Marca como recebida, fixando a data em que o dinheiro entrou.</summary>
    public void Confirmar(DateTime agora, string? quando = null)
    {
        if (Status == StatusPagamento.Cancelado)
        {
            throw new DomainException("Cobranca cancelada nao pode ser confirmada.");
        }

        Status = StatusPagamento.Recebido;
        DataPagamento = AjustarDataDeRecebimento(Status, quando, agora);
    }

    /// <summary>
    /// Cancela a cobranca.
    /// </summary>
    /// <remarks>
    /// Recebimento nao se cancela: o dinheiro ja entrou, e apagar isso do
    /// faturamento sem estorno seria falsear o caixa. Para desfazer, o caminho
    /// e um lancamento de estorno.
    /// </remarks>
    public void Cancelar()
    {
        if (Status == StatusPagamento.Recebido)
        {
            throw new DomainException(
                "Cobranca ja recebida nao pode ser cancelada. Registre um estorno.");
        }

        Status = StatusPagamento.Cancelado;
        DataPagamento = DataSimples.Vazia;
    }

    /// <summary>Guarda o que o Asaas devolveu ao emitir a cobranca.</summary>
    public void RegistrarCobrancaEmitida(DadosDaCobranca cobranca) => Cobranca = cobranca;

    /// <summary>Atualiza os campos editaveis, mantendo status e data coerentes.</summary>
    public void Atualizar(
        decimal valor,
        string? descricao,
        string? dataVencimento,
        string? tipo,
        string? status,
        string? dataPagamento,
        DateTime agora)
    {
        var atualizado = Criar(
            ClienteId, ClienteNome, valor, descricao, dataVencimento,
            tipo, status, dataPagamento, CriadoEm);

        Valor = atualizado.Valor;
        Descricao = atualizado.Descricao;
        DataVencimento = atualizado.DataVencimento;
        Tipo = atualizado.Tipo;
        Status = atualizado.Status;
        DataPagamento = AjustarDataDeRecebimento(atualizado.Status, dataPagamento, agora);
    }

    /// <summary>
    /// Deriva a data de recebimento a partir do status.
    /// </summary>
    /// <remarks>
    /// Recebido sem data assume hoje; qualquer outro status zera a data. Sao os
    /// dois unicos estados coerentes, e ficam garantidos aqui em vez de
    /// dependerem de quem chama lembrar da regra.
    /// </remarks>
    private static DataSimples AjustarDataDeRecebimento(
        StatusPagamento status, string? informada, DateTime agora)
    {
        if (status != StatusPagamento.Recebido)
        {
            return DataSimples.Vazia;
        }

        return DataSimples.TentarCriar(informada, out var data) ? data : DataSimples.De(agora);
    }
}

/// <summary>Artefatos da cobranca emitida pelo Asaas.</summary>
/// <remarks>
/// Value object separado para nao inchar a entidade com sete campos que so
/// existem quando a cobranca e online. Vazio e o estado normal de um
/// recebimento em dinheiro.
/// </remarks>
public sealed record DadosDaCobranca(
    string AsaasPaymentId,
    string PixPayload,
    string PixQrCode,
    string BoletoUrl,
    string NossoNumero)
{
    public static DadosDaCobranca Nenhuma { get; } =
        new(string.Empty, string.Empty, string.Empty, string.Empty, string.Empty);

    public bool Emitida => !string.IsNullOrEmpty(AsaasPaymentId);
}
