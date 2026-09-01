namespace AdriPoltronas.Infrastructure.Configuration;

/// <summary>
/// Chaves e enderecos dos servicos externos.
/// </summary>
/// <remarks>
/// Nenhum valor padrao aqui e segredo: as chaves ficam em variavel de ambiente
/// (<c>Integracoes__ChaveDoAsaas</c>, <c>Integracoes__ChaveDoGemini</c>) ou em
/// arquivo local nao versionado. Chave ausente nao derruba o aplicativo --
/// desliga o recurso, e a tela esconde o botao correspondente.
/// </remarks>
public sealed class OpcoesDeIntegracoes
{
    public const string Secao = "Integracoes";

    /// <summary>Chave da API de cobranca. Vazia desliga a emissao online.</summary>
    public string ChaveDoAsaas { get; init; } = string.Empty;

    /// <summary>Ambiente de testes do provedor de cobranca.</summary>
    /// <remarks>
    /// Verdadeiro por padrao de proposito: errar para o lado do sandbox custa
    /// um teste refeito; errar para producao emite cobranca real a um cliente.
    /// </remarks>
    public bool AsaasSandbox { get; init; } = true;

    /// <summary>Chave do modelo de linguagem usado no palpite de bairro.</summary>
    public string ChaveDoGemini { get; init; } = string.Empty;

    /// <summary>
    /// Identificacao enviada ao servico de geocodificacao.
    /// </summary>
    /// <remarks>
    /// O Nominatim exige um User-Agent que identifique a aplicacao; requisicao
    /// sem ele e recusada.
    /// </remarks>
    public string IdentificacaoDoGeocodificador { get; init; } = "AdriPoltronas/1.0";

    /// <summary>Segundos de espera antes de desistir de uma chamada externa.</summary>
    public int TempoLimiteEmSegundos { get; init; } = 15;
}
