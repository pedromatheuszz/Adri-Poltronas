using AdriPoltronas.Application.Abstractions;
using AdriPoltronas.Application.Common;
using AdriPoltronas.Application.Dtos;
using AdriPoltronas.Domain.Exceptions;
using Microsoft.Extensions.Logging;

namespace AdriPoltronas.Application.UseCases.Entregas;

/// <summary>Marca a entrega como concluida, tirando-a dos alertas.</summary>
public sealed class ConcluirEntrega(
    IEntregaRepository entregas,
    IUnidadeDeTrabalho unidade,
    IRelogio relogio,
    ILogger<ConcluirEntrega> log)
{
    public async Task<Resultado<EntregaDto>> ExecutarAsync(
        int id, CancellationToken cancelamento = default)
    {
        var entrega = await entregas.ObterPorIdAsync(id, cancelamento);
        if (entrega is null)
        {
            return Resultado<EntregaDto>.NaoEncontrado("Entrega nao encontrada.");
        }

        try
        {
            entrega.Concluir();
        }
        catch (DomainException erro)
        {
            return Resultado<EntregaDto>.Invalido([erro.Message]);
        }

        await unidade.ConfirmarAsync(cancelamento);
        log.LogInformation("Entrega {EntregaId} concluida.", id);
        return Resultado<EntregaDto>.Ok(EntregaDto.De(entrega, relogio.Agora));
    }
}

/// <summary>Apaga o agendamento.</summary>
public sealed class ExcluirEntrega(
    IEntregaRepository entregas,
    IUnidadeDeTrabalho unidade,
    ILogger<ExcluirEntrega> log)
{
    public async Task<Resultado> ExecutarAsync(int id, CancellationToken cancelamento = default)
    {
        var entrega = await entregas.ObterPorIdAsync(id, cancelamento);
        if (entrega is null)
        {
            return Resultado.NaoEncontrado("Entrega nao encontrada.");
        }

        entregas.Remover(entrega);
        await unidade.ConfirmarAsync(cancelamento);
        log.LogInformation("Entrega {EntregaId} excluida.", id);
        return Resultado.Ok();
    }
}
