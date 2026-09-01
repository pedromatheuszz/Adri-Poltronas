using AdriPoltronas.Application.Abstractions;
using AdriPoltronas.Application.Common;
using Microsoft.Extensions.Logging;

namespace AdriPoltronas.Application.UseCases.Dados;

/// <summary>
/// Copia de seguranca do banco.
/// </summary>
/// <remarks>
/// Dois formatos porque servem a coisas diferentes: a copia do arquivo
/// restaura o sistema como estava, e o JSON continua legivel daqui a anos,
/// mesmo que o formato do banco mude.
/// </remarks>
public sealed class FazerBackup(IServicoDeBackup backup, ILogger<FazerBackup> log)
{
    public async Task<Resultado<string>> BancoAsync(
        string caminho, CancellationToken cancelamento = default)
    {
        var copia = await backup.CopiarBancoAsync(caminho, cancelamento);
        if (copia.Sucesso)
        {
            log.LogInformation("Copia do banco gravada em {Caminho}.", caminho);
        }

        return copia;
    }

    public async Task<Resultado<string>> JsonAsync(
        string caminho, CancellationToken cancelamento = default)
    {
        var copia = await backup.ExportarJsonAsync(caminho, cancelamento);
        if (copia.Sucesso)
        {
            log.LogInformation("Backup JSON gravado em {Caminho}.", caminho);
        }

        return copia;
    }
}
