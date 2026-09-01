using System.Net.Http.Json;
using System.Text.Json;
using AdriPoltronas.Application.Abstractions;
using AdriPoltronas.Application.Common;
using AdriPoltronas.Domain.Entities;
using AdriPoltronas.Domain.Enums;
using AdriPoltronas.Infrastructure.Configuration;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;

namespace AdriPoltronas.Infrastructure.Integracoes;

/// <summary>
/// Emissao de cobranca pelo Asaas.
/// </summary>
/// <remarks>
/// Fluxo em duas etapas, como a API exige: primeiro o cliente e criado (ou
/// reaproveitado), depois a cobranca. Para Pix ainda ha uma terceira chamada,
/// que busca o QR Code -- a criacao nao o devolve.
///
/// O ambiente padrao e o sandbox. Errar para o sandbox custa um teste refeito;
/// errar para producao emite uma cobranca real ao cliente.
///
/// A chave de acesso vai no cabecalho <c>access_token</c>, configurado uma vez
/// no registro do <see cref="HttpClient"/>. Ela nao aparece em nenhuma
/// mensagem de log desta classe.
/// </remarks>
public sealed class ServicoDeCobrancaAsaas(
    HttpClient http,
    IOptions<OpcoesDeIntegracoes> opcoes,
    ILogger<ServicoDeCobrancaAsaas> log) : IServicoDeCobranca
{
    private const string BaseSandbox = "https://api-sandbox.asaas.com/v3";
    private const string BaseProducao = "https://api.asaas.com/v3";

    private readonly OpcoesDeIntegracoes _opcoes = opcoes.Value;

    public bool Configurado => !string.IsNullOrWhiteSpace(_opcoes.ChaveDoAsaas);

    private string Base => _opcoes.AsaasSandbox ? BaseSandbox : BaseProducao;

    public async Task<Resultado<DadosDaCobranca>> EmitirAsync(
        Pagamento pagamento, CancellationToken cancelamento = default)
    {
        if (!Configurado)
        {
            return Resultado<DadosDaCobranca>.Invalido(["Cobranca online nao configurada."]);
        }

        try
        {
            var cliente = await CriarClienteAsync(pagamento.ClienteNome, cancelamento);
            if (cliente is null)
            {
                return Resultado<DadosDaCobranca>.Invalido(
                    ["Nao foi possivel registrar o cliente no provedor de cobranca."]);
            }

            var forma = pagamento.Tipo == TipoPagamento.Boleto ? "BOLETO" : "PIX";
            var corpo = new
            {
                customer = cliente,
                billingType = forma,
                value = (double)pagamento.Valor.Valor,
                dueDate = pagamento.DataVencimento.Texto,
                description = pagamento.Descricao,
            };

            using var resposta = await http.PostAsJsonAsync(
                $"{Base}/payments", corpo, cancelamento);
            var criada = await LerAsync(resposta, cancelamento);
            if (criada is null)
            {
                return Resultado<DadosDaCobranca>.Invalido(
                    ["O provedor recusou a emissao da cobranca."]);
            }

            var id = Texto(criada, "id");
            var boleto = Texto(criada, "bankSlipUrl");
            var nossoNumero = Texto(criada, "nossoNumero");

            // O Pix so devolve QR Code em chamada separada.
            var (payload, imagem) = forma == "PIX"
                ? await ObterPixAsync(id, cancelamento)
                : (string.Empty, string.Empty);

            return Resultado<DadosDaCobranca>.Ok(
                new DadosDaCobranca(id, payload, imagem, boleto, nossoNumero));
        }
        catch (Exception erro)
            when (erro is HttpRequestException or TaskCanceledException or JsonException)
        {
            log.LogError(erro, "Falha ao falar com o provedor de cobranca.");
            return Resultado<DadosDaCobranca>.Invalido(
                ["Nao foi possivel falar com o provedor de cobranca. Tente novamente."]);
        }
    }

    public async Task<Resultado> CancelarAsync(
        string cobrancaId, CancellationToken cancelamento = default)
    {
        if (!Configurado || string.IsNullOrWhiteSpace(cobrancaId))
        {
            return Resultado.Invalido(["Cobranca online nao configurada."]);
        }

        try
        {
            using var resposta = await http.DeleteAsync(
                $"{Base}/payments/{cobrancaId}", cancelamento);
            return resposta.IsSuccessStatusCode
                ? Resultado.Ok()
                : Resultado.Invalido(["O provedor recusou o cancelamento da cobranca."]);
        }
        catch (Exception erro) when (erro is HttpRequestException or TaskCanceledException)
        {
            log.LogError(erro, "Falha ao cancelar a cobranca {Cobranca}.", cobrancaId);
            return Resultado.Invalido(["Nao foi possivel falar com o provedor de cobranca."]);
        }
    }

    /// <summary>Registra o cliente no provedor e devolve o identificador dele.</summary>
    private async Task<string?> CriarClienteAsync(string nome, CancellationToken cancelamento)
    {
        var corpo = new { name = string.IsNullOrWhiteSpace(nome) ? "Cliente" : nome };
        using var resposta = await http.PostAsJsonAsync($"{Base}/customers", corpo, cancelamento);
        var criado = await LerAsync(resposta, cancelamento);
        var id = criado is null ? string.Empty : Texto(criado, "id");
        return string.IsNullOrEmpty(id) ? null : id;
    }

    /// <summary>Busca o Pix copia-e-cola e a imagem do QR Code da cobranca.</summary>
    private async Task<(string Payload, string Imagem)> ObterPixAsync(
        string cobrancaId, CancellationToken cancelamento)
    {
        if (string.IsNullOrEmpty(cobrancaId))
        {
            return (string.Empty, string.Empty);
        }

        using var resposta = await http.GetAsync(
            $"{Base}/payments/{cobrancaId}/pixQrCode", cancelamento);
        var pix = await LerAsync(resposta, cancelamento);

        return pix is null
            // O codigo Pix as vezes demora a ficar pronto. A cobranca ja existe,
            // entao vale devolve-la sem o QR a perder a emissao inteira.
            ? (string.Empty, string.Empty)
            : (Texto(pix, "payload"), Texto(pix, "encodedImage"));
    }

    private async Task<JsonElement?> LerAsync(
        HttpResponseMessage resposta, CancellationToken cancelamento)
    {
        var corpo = await resposta.Content.ReadAsStringAsync(cancelamento);
        if (!resposta.IsSuccessStatusCode)
        {
            // O corpo do erro do Asaas descreve o campo recusado e nao contem a
            // chave de acesso; registra-lo e o que torna a falha diagnosticavel.
            log.LogWarning(
                "Provedor de cobranca respondeu {Situacao}: {Corpo}",
                resposta.StatusCode, corpo);
            return null;
        }

        return string.IsNullOrWhiteSpace(corpo)
            ? null
            : JsonDocument.Parse(corpo).RootElement.Clone();
    }

    private static string Texto(JsonElement? elemento, string campo) =>
        elemento is { } valor &&
        valor.TryGetProperty(campo, out var propriedade) &&
        propriedade.ValueKind == JsonValueKind.String
            ? propriedade.GetString() ?? string.Empty
            : string.Empty;
}
