using AdriPoltronas.Application.Abstractions;
using AdriPoltronas.Application.Dtos;

namespace AdriPoltronas.Application.UseCases.Clientes;

/// <summary>Lista os clientes, filtrando por nome, cidade ou bairro.</summary>
/// <remarks>
/// Nao devolve <c>Resultado</c>: uma busca sem correspondencia e uma lista
/// vazia, nao uma falha.
/// </remarks>
public sealed class BuscarClientes(IClienteRepository clientes)
{
    public async Task<IReadOnlyList<ClienteDto>> ExecutarAsync(
        string? termo, CancellationToken cancelamento = default)
    {
        var encontrados = await clientes.BuscarAsync(termo, cancelamento);
        return [.. encontrados.Select(ClienteDto.De)];
    }
}
