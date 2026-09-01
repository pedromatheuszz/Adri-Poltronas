using System.Net.Http.Json;
using System.Text.Json;
using AdriPoltronas.Application.Abstractions;
using AdriPoltronas.Infrastructure.Configuration;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;

namespace AdriPoltronas.Infrastructure.Integracoes;

/// <summary>
/// Palpite de bairro a partir do CEP, usando o Gemini.
/// </summary>
/// <remarks>
/// So entra em cena quando o ViaCEP nao devolveu bairro. E um palpite: o
/// formulario preenche o campo mas continua editavel, e o operador confere. Por
/// isso qualquer falha aqui devolve nulo em silencio -- o cadastro nao depende
/// disso para funcionar.
/// </remarks>
public sealed class SugestaoDeBairroGemini(
    HttpClient http,
    IOptions<OpcoesDeIntegracoes> opcoes,
    ILogger<SugestaoDeBairroGemini> log) : ISugestaoDeBairro
{
    private const string Modelo = "gemini-2.0-flash";

    private readonly OpcoesDeIntegracoes _opcoes = opcoes.Value;

    public bool Configurado => !string.IsNullOrWhiteSpace(_opcoes.ChaveDoGemini);

    public async Task<string?> SugerirAsync(
        string cep, string rua, string cidade, CancellationToken cancelamento = default)
    {
        if (!Configurado)
        {
            return null;
        }

        var pergunta =
            $"Para o CEP brasileiro {cep}, na cidade {cidade}, rua {rua}, qual o bairro mais " +
            "provavel? Responda apenas com o nome do bairro, sem pontuacao nem explicacao.";

        var corpo = new
        {
            contents = new[] { new { parts = new[] { new { text = pergunta } } } },
            generationConfig = new { temperature = 0.3, maxOutputTokens = 200 },
        };

        try
        {
            // A chave vai na query porque e o que a API do Gemini aceita. Ela
            // nunca chega a um log: nenhuma mensagem desta classe inclui o
            // endereco montado.
            var endereco =
                $"https://generativelanguage.googleapis.com/v1beta/models/{Modelo}" +
                $":generateContent?key={Uri.EscapeDataString(_opcoes.ChaveDoGemini)}";

            using var resposta = await http.PostAsJsonAsync(endereco, corpo, cancelamento);
            if (!resposta.IsSuccessStatusCode)
            {
                log.LogWarning(
                    "Sugestao de bairro recusada pelo servico: {Situacao}.", resposta.StatusCode);
                return null;
            }

            using var conteudo =
                await resposta.Content.ReadFromJsonAsync<JsonDocument>(cancelamento);
            return PrimeiroTexto(conteudo);
        }
        catch (Exception erro)
            when (erro is HttpRequestException or TaskCanceledException or JsonException)
        {
            log.LogWarning(erro, "Sugestao de bairro indisponivel.");
            return null;
        }
    }

    /// <summary>Extrai o texto da primeira resposta, tolerando formato inesperado.</summary>
    private static string? PrimeiroTexto(JsonDocument? documento)
    {
        if (documento is null ||
            !documento.RootElement.TryGetProperty("candidates", out var candidatos) ||
            candidatos.ValueKind != JsonValueKind.Array ||
            candidatos.GetArrayLength() == 0)
        {
            return null;
        }

        if (!candidatos[0].TryGetProperty("content", out var conteudo) ||
            !conteudo.TryGetProperty("parts", out var partes) ||
            partes.ValueKind != JsonValueKind.Array ||
            partes.GetArrayLength() == 0 ||
            !partes[0].TryGetProperty("text", out var texto))
        {
            return null;
        }

        var limpo = texto.GetString()?.Trim().Trim('"', '.');
        return string.IsNullOrWhiteSpace(limpo) ? null : limpo.Trim();
    }
}
