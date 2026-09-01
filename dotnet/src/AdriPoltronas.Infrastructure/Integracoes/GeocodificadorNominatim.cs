using System.Collections.Concurrent;
using System.Net.Http.Json;
using System.Text.Json;
using System.Text.Json.Serialization;
using AdriPoltronas.Application.Abstractions;
using AdriPoltronas.Infrastructure.Sistema;
using Microsoft.Extensions.Logging;

namespace AdriPoltronas.Infrastructure.Integracoes;

/// <summary>
/// Converte endereco em coordenada usando o Nominatim (OpenStreetMap).
/// </summary>
/// <remarks>
/// O servico e publico e limita uma requisicao por segundo. Sem cache, abrir a
/// aba do mapa com cinquenta clientes levaria quase um minuto e ainda correria
/// risco de bloqueio -- por isso o resultado e guardado em arquivo, na pasta de
/// dados do usuario, e sobrevive ao fechamento do aplicativo.
///
/// O cache e arquivo, e nao tabela: nao e dado do negocio, e uma tabela nova
/// divergiria do schema que o backend Python compartilha.
/// </remarks>
public sealed class GeocodificadorNominatim : IGeocodificador, IDisposable
{
    private const string Endereco = "https://nominatim.openstreetmap.org/search";

    /// <summary>Intervalo minimo entre chamadas, exigido pelo servico.</summary>
    private static readonly TimeSpan EsperaEntreChamadas = TimeSpan.FromMilliseconds(1100);

    private readonly HttpClient _http;
    private readonly ILogger<GeocodificadorNominatim> _log;
    private readonly ConcurrentDictionary<string, Coordenada> _cache;
    private readonly SemaphoreSlim _vez = new(1, 1);
    private readonly string _arquivo;
    private DateTime _ultimaChamada = DateTime.MinValue;

    public GeocodificadorNominatim(HttpClient http, ILogger<GeocodificadorNominatim> log)
    {
        _http = http;
        _log = log;
        _arquivo = Path.Combine(PastaDeDados.Raiz(), "geocache.json");
        _cache = new ConcurrentDictionary<string, Coordenada>(Ler(_arquivo, log));
    }

    public async Task<Coordenada?> LocalizarAsync(
        string endereco, string cidade, string cep, CancellationToken cancelamento = default)
    {
        var consulta = string.Join(", ", new[] { endereco, cidade, cep, "Brasil" }
            .Where(parte => !string.IsNullOrWhiteSpace(parte)));

        if (consulta.Length <= "Brasil".Length)
        {
            return null;
        }

        var chave = consulta.ToLowerInvariant();
        if (_cache.TryGetValue(chave, out var guardada))
        {
            return guardada;
        }

        await _vez.WaitAsync(cancelamento);
        try
        {
            // Outra chamada pode ter resolvido o mesmo endereco enquanto esta
            // esperava a vez.
            if (_cache.TryGetValue(chave, out guardada))
            {
                return guardada;
            }

            await RespeitarLimiteAsync(cancelamento);

            var url = $"{Endereco}?format=json&limit=1&q={Uri.EscapeDataString(consulta)}";
            var resultados = await _http.GetFromJsonAsync<List<RespostaDoNominatim>>(
                url, cancelamento);

            var primeiro = resultados?.FirstOrDefault();
            if (primeiro is null ||
                !double.TryParse(primeiro.Lat, System.Globalization.NumberStyles.Float,
                    System.Globalization.CultureInfo.InvariantCulture, out var latitude) ||
                !double.TryParse(primeiro.Lon, System.Globalization.NumberStyles.Float,
                    System.Globalization.CultureInfo.InvariantCulture, out var longitude))
            {
                return null;
            }

            var coordenada = new Coordenada(latitude, longitude);
            _cache[chave] = coordenada;
            Gravar();
            return coordenada;
        }
        catch (Exception erro)
            when (erro is HttpRequestException or TaskCanceledException or JsonException)
        {
            _log.LogWarning(erro, "Geocodificacao de {Consulta} indisponivel.", consulta);
            return null;
        }
        finally
        {
            _vez.Release();
        }
    }

    public void Dispose() => _vez.Dispose();

    private async Task RespeitarLimiteAsync(CancellationToken cancelamento)
    {
        var desdeAUltima = DateTime.UtcNow - _ultimaChamada;
        if (desdeAUltima < EsperaEntreChamadas)
        {
            await Task.Delay(EsperaEntreChamadas - desdeAUltima, cancelamento);
        }

        _ultimaChamada = DateTime.UtcNow;
    }

    private static Dictionary<string, Coordenada> Ler(string arquivo, ILogger log)
    {
        try
        {
            return File.Exists(arquivo)
                ? JsonSerializer.Deserialize<Dictionary<string, Coordenada>>(
                      File.ReadAllText(arquivo)) ?? []
                : [];
        }
        catch (Exception erro) when (erro is IOException or JsonException)
        {
            // Cache corrompido nao impede o mapa de funcionar: recomeca vazio.
            log.LogWarning(erro, "Cache de coordenadas ilegivel; sera refeito.");
            return [];
        }
    }

    private void Gravar()
    {
        try
        {
            File.WriteAllText(_arquivo, JsonSerializer.Serialize(_cache));
        }
        catch (IOException erro)
        {
            _log.LogWarning(erro, "Nao foi possivel gravar o cache de coordenadas.");
        }
    }

    private sealed record RespostaDoNominatim
    {
        [JsonPropertyName("lat")] public string? Lat { get; init; }
        [JsonPropertyName("lon")] public string? Lon { get; init; }
    }
}
