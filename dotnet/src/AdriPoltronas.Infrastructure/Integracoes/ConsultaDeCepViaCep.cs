using System.Net.Http.Json;
using System.Text.Json.Serialization;
using AdriPoltronas.Application.Abstractions;
using AdriPoltronas.Application.Dtos;
using Microsoft.Extensions.Logging;

namespace AdriPoltronas.Infrastructure.Integracoes;

/// <summary>Consulta de CEP no ViaCEP.</summary>
/// <remarks>
/// Servico fora do ar devolve nulo, e nao excecao: o formulario continua
/// utilizavel com o endereco digitado a mao. Perder a conveniencia e aceitavel;
/// travar o cadastro por causa dela nao e.
/// </remarks>
public sealed class ConsultaDeCepViaCep(HttpClient http, ILogger<ConsultaDeCepViaCep> log)
    : IConsultaDeCep
{
    public async Task<EnderecoConsultado?> ConsultarAsync(
        string cep, CancellationToken cancelamento = default)
    {
        var digitos = new string([.. cep.Where(char.IsDigit)]);
        if (digitos.Length != 8)
        {
            return null;
        }

        try
        {
            var resposta = await http.GetFromJsonAsync<RespostaDoViaCep>(
                $"https://viacep.com.br/ws/{digitos}/json/", cancelamento);

            if (resposta is null || resposta.Erro)
            {
                return null;
            }

            return new EnderecoConsultado(
                resposta.Cep ?? string.Empty,
                resposta.Logradouro ?? string.Empty,
                resposta.Bairro ?? string.Empty,
                resposta.Localidade ?? string.Empty,
                resposta.Uf ?? string.Empty);
        }
        catch (Exception erro) when (erro is HttpRequestException or TaskCanceledException)
        {
            log.LogWarning(erro, "Consulta do CEP {Cep} falhou.", digitos);
            return null;
        }
    }

    private sealed record RespostaDoViaCep
    {
        [JsonPropertyName("cep")] public string? Cep { get; init; }
        [JsonPropertyName("logradouro")] public string? Logradouro { get; init; }
        [JsonPropertyName("bairro")] public string? Bairro { get; init; }
        [JsonPropertyName("localidade")] public string? Localidade { get; init; }
        [JsonPropertyName("uf")] public string? Uf { get; init; }
        [JsonPropertyName("erro")] public bool Erro { get; init; }
    }
}
