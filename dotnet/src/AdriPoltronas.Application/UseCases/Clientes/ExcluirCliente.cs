using AdriPoltronas.Application.Abstractions;
using AdriPoltronas.Application.Common;
using AdriPoltronas.Domain.Entities;
using Microsoft.Extensions.Logging;

namespace AdriPoltronas.Application.UseCases.Clientes;

/// <summary>Remove um cliente, deixando o rastro no historico.</summary>
public sealed class ExcluirCliente(
    IClienteRepository clientes,
    IHistoricoRepository historico,
    IUnidadeDeTrabalho unidade,
    IRelogio relogio,
    ILogger<ExcluirCliente> log)
{
    public async Task<Resultado> ExecutarAsync(int id, CancellationToken cancelamento = default)
    {
        var cliente = await clientes.ObterPorIdAsync(id, cancelamento);
        if (cliente is null)
        {
            return Resultado.NaoEncontrado($"Cliente {id} nao encontrado.");
        }

        // O registro e montado ANTES da remocao: depois dela o nome e o
        // endereco que a auditoria precisa registrar ja teriam se perdido.
        var registro = RegistroHistorico.Exclusao(cliente, relogio.Agora);
        clientes.Remover(cliente);
        historico.Adicionar(registro);
        await unidade.ConfirmarAsync(cancelamento);

        log.LogInformation("Cliente {ClienteId} excluido.", id);
        return Resultado.Ok();
    }
}
