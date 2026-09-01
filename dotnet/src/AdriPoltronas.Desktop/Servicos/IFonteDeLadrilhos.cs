namespace AdriPoltronas.Desktop.Servicos;

/// <summary>
/// Imagens do mapa, por coordenada de ladrilho.
/// </summary>
/// <remarks>
/// O controle do mapa depende desta interface, e nao de <c>HttpClient</c>: sem
/// isso ele so poderia ser exercitado com rede disponivel, e o desenho dos
/// marcadores -- que e a parte com regra -- ficaria sem teste.
/// </remarks>
public interface IFonteDeLadrilhos
{
    /// <summary>Bytes PNG do ladrilho, ou nulo quando nao ha como obter.</summary>
    Task<byte[]?> ObterAsync(int zoom, int x, int y, CancellationToken cancelamento = default);
}
