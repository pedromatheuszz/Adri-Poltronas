using AdriPoltronas.Application.Abstractions;
using AdriPoltronas.Application.Dtos;
using AdriPoltronas.Domain.Enums;

namespace AdriPoltronas.Application.UseCases.Mapa;

/// <summary>
/// Coordenadas dos clientes para o mapa.
/// </summary>
/// <remarks>
/// Cliente sem endereco resolvivel simplesmente nao entra na lista. Nao e
/// falha: o mapa mostra quem da para mostrar, e a tela informa quantos
/// ficaram de fora.
/// </remarks>
public sealed class ObterPontosDoMapa(
    IClienteRepository clientes,
    IGeocodificador geocodificador)
{
    public async Task<IReadOnlyList<PontoNoMapa>> ExecutarAsync(
        CancellationToken cancelamento = default)
    {
        var cadastrados = await clientes.BuscarAsync(null, cancelamento);
        var pontos = new List<PontoNoMapa>(cadastrados.Count);

        foreach (var cliente in cadastrados)
        {
            cancelamento.ThrowIfCancellationRequested();

            var endereco = cliente.Endereco;
            var coordenada = await geocodificador.LocalizarAsync(
                endereco.Rua, endereco.Cidade, endereco.Cep.Valor, cancelamento);

            if (coordenada is null)
            {
                continue;
            }

            pontos.Add(new PontoNoMapa(
                cliente.Id,
                cliente.Nome,
                string.Join(", ", new[] { endereco.Rua, endereco.Bairro, endereco.Cidade }
                    .Where(p => !string.IsNullOrWhiteSpace(p))),
                cliente.Tipo.ParaTexto(),
                coordenada.Value.Latitude,
                coordenada.Value.Longitude));
        }

        return pontos;
    }
}
