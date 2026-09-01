using AdriPoltronas.Application.Abstractions;
using AdriPoltronas.Application.Common;
using AdriPoltronas.Application.Dtos;
using AdriPoltronas.Domain.Exceptions;
using Microsoft.Extensions.Logging;

namespace AdriPoltronas.Application.UseCases.Pagamentos;

/// <summary>Confirma o recebimento de uma cobranca.</summary>
public sealed class ConfirmarPagamento(
    IPagamentoRepository pagamentos,
    IUnidadeDeTrabalho unidade,
    IRelogio relogio,
    ILogger<ConfirmarPagamento> log)
{
    public async Task<Resultado<PagamentoDto>> ExecutarAsync(
        int id, string? quando = null, CancellationToken cancelamento = default)
    {
        var pagamento = await pagamentos.ObterPorIdAsync(id, cancelamento);
        if (pagamento is null)
        {
            return Resultado<PagamentoDto>.NaoEncontrado("Cobranca nao encontrada.");
        }

        try
        {
            pagamento.Confirmar(relogio.Agora, quando);
        }
        catch (DomainException erro)
        {
            // Confirmar uma cobranca cancelada nao e dado invalido: e uma
            // transicao que o negocio proibe.
            return Resultado<PagamentoDto>.Invalido([erro.Message]);
        }

        await unidade.ConfirmarAsync(cancelamento);
        log.LogInformation("Pagamento {PagamentoId} confirmado.", id);
        return Resultado<PagamentoDto>.Ok(PagamentoDto.De(pagamento, relogio.Agora));
    }
}

/// <summary>Cancela uma cobranca ainda nao recebida.</summary>
public sealed class CancelarPagamento(
    IPagamentoRepository pagamentos,
    IUnidadeDeTrabalho unidade,
    IRelogio relogio,
    ILogger<CancelarPagamento> log)
{
    public async Task<Resultado<PagamentoDto>> ExecutarAsync(
        int id, CancellationToken cancelamento = default)
    {
        var pagamento = await pagamentos.ObterPorIdAsync(id, cancelamento);
        if (pagamento is null)
        {
            return Resultado<PagamentoDto>.NaoEncontrado("Cobranca nao encontrada.");
        }

        try
        {
            pagamento.Cancelar();
        }
        catch (DomainException erro)
        {
            return Resultado<PagamentoDto>.Invalido([erro.Message]);
        }

        await unidade.ConfirmarAsync(cancelamento);
        log.LogInformation("Pagamento {PagamentoId} cancelado.", id);
        return Resultado<PagamentoDto>.Ok(PagamentoDto.De(pagamento, relogio.Agora));
    }
}

/// <summary>Apaga o lancamento.</summary>
public sealed class ExcluirPagamento(
    IPagamentoRepository pagamentos,
    IUnidadeDeTrabalho unidade,
    ILogger<ExcluirPagamento> log)
{
    public async Task<Resultado> ExecutarAsync(int id, CancellationToken cancelamento = default)
    {
        var pagamento = await pagamentos.ObterPorIdAsync(id, cancelamento);
        if (pagamento is null)
        {
            return Resultado.NaoEncontrado("Cobranca nao encontrada.");
        }

        pagamentos.Remover(pagamento);
        await unidade.ConfirmarAsync(cancelamento);
        log.LogInformation("Pagamento {PagamentoId} excluido.", id);
        return Resultado.Ok();
    }
}
