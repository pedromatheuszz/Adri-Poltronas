using AdriPoltronas.Application.Abstractions;
using AdriPoltronas.Application.Common;
using AdriPoltronas.Application.Dtos;
using AdriPoltronas.Domain.Entities;
using AdriPoltronas.Domain.Exceptions;
using Microsoft.Extensions.Logging;

namespace AdriPoltronas.Application.UseCases.Entregas;

/// <summary>Marca uma entrega para um cliente existente.</summary>
public sealed class AgendarEntrega(
    IEntregaRepository entregas,
    IClienteRepository clientes,
    IUnidadeDeTrabalho unidade,
    IRelogio relogio,
    ILogger<AgendarEntrega> log)
{
    public async Task<Resultado<EntregaDto>> ExecutarAsync(
        DadosDaEntrega dados, CancellationToken cancelamento = default)
    {
        var cliente = await clientes.ObterPorIdAsync(dados.ClienteId, cancelamento);
        if (cliente is null)
        {
            return Resultado<EntregaDto>.NaoEncontrado("Cliente nao encontrado.");
        }

        EntregaAgendada entrega;
        try
        {
            entrega = EntregaAgendada.Criar(
                cliente.Id, cliente.Nome, dados.DataEntrega,
                dados.HoraEntrega, dados.Descricao, relogio.Agora);
        }
        catch (ValidacaoException erro)
        {
            return Resultado<EntregaDto>.Invalido(erro.Erros);
        }

        entregas.Adicionar(entrega);
        await unidade.ConfirmarAsync(cancelamento);

        log.LogInformation(
            "Entrega {EntregaId} agendada para o cliente {ClienteId}.", entrega.Id, cliente.Id);
        return Resultado<EntregaDto>.Ok(EntregaDto.De(entrega, relogio.Agora));
    }
}
