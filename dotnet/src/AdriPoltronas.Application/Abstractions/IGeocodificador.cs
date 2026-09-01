namespace AdriPoltronas.Application.Abstractions;

/// <summary>Coordenadas de um endereco.</summary>
public readonly record struct Coordenada(double Latitude, double Longitude);

/// <summary>
/// Conversao de endereco em coordenada.
/// </summary>
/// <remarks>
/// O servico publico usado limita requisicoes por segundo, entao a
/// implementacao guarda o que ja resolveu. O cache fica na Infrastructure: e
/// detalhe do provedor, nao regra do aplicativo.
/// </remarks>
public interface IGeocodificador
{
    Task<Coordenada?> LocalizarAsync(
        string endereco, string cidade, string cep, CancellationToken cancelamento = default);
}
