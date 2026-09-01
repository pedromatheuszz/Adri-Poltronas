using AdriPoltronas.Application.Abstractions;
using AdriPoltronas.Application.Common;
using AdriPoltronas.Application.Dtos;
using Microsoft.Extensions.Logging;

namespace AdriPoltronas.Application.UseCases.Relatorios;

/// <summary>
/// Grava o relatorio em arquivo.
/// </summary>
/// <remarks>
/// Reaproveita <see cref="GerarRelatorio"/> em vez de repetir a consulta: o
/// arquivo exportado precisa conter exatamente o que a tela mostrou, e duas
/// consultas parecidas divergem na primeira vez que alguem ajusta uma delas.
/// </remarks>
public sealed class ExportarRelatorio(
    GerarRelatorio relatorio,
    IExportadorDePlanilha exportador,
    ILogger<ExportarRelatorio> log)
{
    private static readonly string[] Cabecalhos =
        ["Id", "Nome", "Cidade", "Bairro", "Tipo", "Cadastrado em"];

    public async Task<Resultado> ExecutarAsync(
        FiltroDeRelatorio filtro,
        string caminho,
        FormatoDeArquivo formato,
        CancellationToken cancelamento = default)
    {
        var dados = await relatorio.ExecutarAsync(filtro, cancelamento);
        if (dados.Total == 0)
        {
            return Resultado.Invalido(["Nenhum cliente atende aos filtros escolhidos."]);
        }

        var linhas = dados.Linhas
            .Select(l => (IReadOnlyList<string>)new[]
            {
                l.Id.ToString(),
                l.Nome,
                l.Cidade,
                l.Bairro,
                l.Tipo,
                l.CriadoEm,
            })
            .ToList();

        var gravacao = await exportador.ExportarAsync(
            caminho, formato, "Relatorio de Clientes", Cabecalhos, linhas, cancelamento);

        if (gravacao.Sucesso)
        {
            log.LogInformation(
                "Relatorio com {Total} clientes exportado para {Caminho}.", dados.Total, caminho);
        }

        return gravacao;
    }
}
