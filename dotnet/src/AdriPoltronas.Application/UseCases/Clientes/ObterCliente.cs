using AdriPoltronas.Application.Abstractions;
using AdriPoltronas.Application.Common;
using AdriPoltronas.Application.Dtos;

namespace AdriPoltronas.Application.UseCases.Clientes;

/// <summary>Carrega um cliente pelo identificador.</summary>
public sealed class ObterCliente(IClienteRepository clientes)
{
    public async Task<Resultado<ClienteDto>> ExecutarAsync(
        int id, CancellationToken cancelamento = default)
    {
        var cliente = await clientes.ObterPorIdAsync(id, cancelamento);
        return cliente is null
            ? Resultado<ClienteDto>.NaoEncontrado($"Cliente {id} nao encontrado.")
            : Resultado<ClienteDto>.Ok(ClienteDto.De(cliente));
    }
}
