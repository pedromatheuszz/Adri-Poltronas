using AdriPoltronas.Application.Common;
using AdriPoltronas.Domain.Entities;

namespace AdriPoltronas.Application.Abstractions;

/// <summary>
/// Emissao de cobranca online.
/// </summary>
/// <remarks>
/// A implementacao conversa com o Asaas. A interface nao menciona isso: trocar
/// de adquirente nao deve alcancar a Application, e um teste de caso de uso
/// nao pode depender de rede.
/// </remarks>
public interface IServicoDeCobranca
{
    /// <summary>Falso quando falta chave de API; a tela esconde o botao.</summary>
    bool Configurado { get; }

    /// <summary>Emite a cobranca e devolve os artefatos, Pix ou boleto.</summary>
    Task<Resultado<DadosDaCobranca>> EmitirAsync(
        Pagamento pagamento, CancellationToken cancelamento = default);

    Task<Resultado> CancelarAsync(string cobrancaId, CancellationToken cancelamento = default);
}
