using AdriPoltronas.Infrastructure.Sistema;
using Microsoft.Extensions.Logging;

namespace AdriPoltronas.Desktop.Servicos;

/// <summary>
/// Ladrilhos do OpenStreetMap, com cache em disco.
/// </summary>
/// <remarks>
/// O cache nao e otimizacao: a politica de uso do servico publico pede que o
/// cliente nao rebusque o mesmo ladrilho. Sem ele, cada arrastar do mapa
/// dispararia dezenas de requisicoes repetidas e o aplicativo seria bloqueado.
///
/// Falha de rede devolve nulo, e o mapa desenha o fundo liso com os
/// marcadores por cima -- continua util mesmo offline.
/// </remarks>
public sealed class FonteDeLadrilhosOsm(
    HttpClient http, ILogger<FonteDeLadrilhosOsm> log) : IFonteDeLadrilhos
{
    private readonly SemaphoreSlim _limite = new(4, 4);

    public async Task<byte[]?> ObterAsync(
        int zoom, int x, int y, CancellationToken cancelamento = default)
    {
        var arquivo = Path.Combine(Pasta(zoom, x), $"{y}.png");
        if (File.Exists(arquivo))
        {
            try
            {
                return await File.ReadAllBytesAsync(arquivo, cancelamento);
            }
            catch (IOException)
            {
                // Arquivo truncado por um fechamento no meio da gravacao:
                // rebusca em vez de devolver imagem quebrada.
            }
        }

        // Quatro por vez: o servico publico recusa rajadas.
        await _limite.WaitAsync(cancelamento);
        try
        {
            var bytes = await http.GetByteArrayAsync(
                $"https://tile.openstreetmap.org/{zoom}/{x}/{y}.png", cancelamento);

            Directory.CreateDirectory(Pasta(zoom, x));
            await File.WriteAllBytesAsync(arquivo, bytes, cancelamento);
            return bytes;
        }
        catch (Exception erro)
            when (erro is HttpRequestException or TaskCanceledException or IOException)
        {
            log.LogDebug(erro, "Ladrilho {Zoom}/{X}/{Y} indisponivel.", zoom, x, y);
            return null;
        }
        finally
        {
            _limite.Release();
        }
    }

    private static string Pasta(int zoom, int x) =>
        Path.Combine(PastaDeDados.Raiz(), "ladrilhos", zoom.ToString(), x.ToString());
}
