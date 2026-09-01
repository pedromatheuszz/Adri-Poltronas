using System.Globalization;
using System.Text;
using AdriPoltronas.Application.Abstractions;
using AdriPoltronas.Application.Common;
using AdriPoltronas.Application.Dtos;
using ClosedXML.Excel;
using Microsoft.Extensions.Logging;

namespace AdriPoltronas.Infrastructure.Arquivos;

/// <summary>Grava listas em CSV, XLSX ou JSON.</summary>
/// <remarks>
/// O CSV sai com BOM UTF-8 de proposito: sem ele o Excel em portugues abre
/// acentuacao trocada, e a planilha exportada e justamente o que o operador
/// leva para o contador.
/// </remarks>
public sealed class ExportadorDePlanilha(ILogger<ExportadorDePlanilha> log)
    : IExportadorDePlanilha
{
    public async Task<Resultado> ExportarAsync(
        string caminho,
        FormatoDeArquivo formato,
        string titulo,
        IReadOnlyList<string> cabecalhos,
        IReadOnlyList<IReadOnlyList<string>> linhas,
        CancellationToken cancelamento = default)
    {
        try
        {
            var pasta = Path.GetDirectoryName(caminho);
            if (!string.IsNullOrEmpty(pasta))
            {
                Directory.CreateDirectory(pasta);
            }

            switch (formato)
            {
                case FormatoDeArquivo.Xlsx:
                    GravarXlsx(caminho, titulo, cabecalhos, linhas);
                    break;

                case FormatoDeArquivo.Json:
                    await GravarJsonAsync(caminho, cabecalhos, linhas, cancelamento);
                    break;

                default:
                    await GravarCsvAsync(caminho, cabecalhos, linhas, cancelamento);
                    break;
            }

            return Resultado.Ok();
        }
        catch (Exception erro) when (erro is IOException or UnauthorizedAccessException)
        {
            // Arquivo aberto no Excel e o caso comum. A mensagem diz o que
            // fazer, em vez de mostrar o texto do sistema.
            log.LogWarning(erro, "Falha ao gravar {Caminho}.", caminho);
            return Resultado.Invalido(
                ["Nao foi possivel gravar o arquivo. Feche-o se estiver aberto e tente de novo."]);
        }
    }

    private static void GravarXlsx(
        string caminho,
        string titulo,
        IReadOnlyList<string> cabecalhos,
        IReadOnlyList<IReadOnlyList<string>> linhas)
    {
        using var planilha = new XLWorkbook();
        var aba = planilha.Worksheets.Add(NomeDeAbaValido(titulo));

        for (var coluna = 0; coluna < cabecalhos.Count; coluna++)
        {
            aba.Cell(1, coluna + 1).Value = cabecalhos[coluna];
        }

        aba.Row(1).Style.Font.Bold = true;

        for (var linha = 0; linha < linhas.Count; linha++)
        {
            for (var coluna = 0; coluna < linhas[linha].Count; coluna++)
            {
                aba.Cell(linha + 2, coluna + 1).Value = linhas[linha][coluna];
            }
        }

        aba.Columns().AdjustToContents();
        planilha.SaveAs(caminho);
    }

    /// <summary>O Excel recusa aba com mais de 31 caracteres ou com barras.</summary>
    private static string NomeDeAbaValido(string titulo)
    {
        var limpo = new string([.. titulo.Where(c => !"[]:*?/\\".Contains(c))]).Trim();
        if (limpo.Length == 0)
        {
            limpo = "Dados";
        }

        return limpo.Length <= 31 ? limpo : limpo[..31];
    }

    private static async Task GravarCsvAsync(
        string caminho,
        IReadOnlyList<string> cabecalhos,
        IReadOnlyList<IReadOnlyList<string>> linhas,
        CancellationToken cancelamento)
    {
        var texto = new StringBuilder();
        texto.AppendLine(string.Join(";", cabecalhos.Select(Escapar)));

        foreach (var linha in linhas)
        {
            texto.AppendLine(string.Join(";", linha.Select(Escapar)));
        }

        // Ponto e virgula e BOM: e o que o Excel em portugues abre direito.
        await File.WriteAllTextAsync(
            caminho, texto.ToString(), new UTF8Encoding(true), cancelamento);
    }

    private static async Task GravarJsonAsync(
        string caminho,
        IReadOnlyList<string> cabecalhos,
        IReadOnlyList<IReadOnlyList<string>> linhas,
        CancellationToken cancelamento)
    {
        var registros = linhas.Select(linha => cabecalhos
            .Select((titulo, indice) => new
            {
                Titulo = titulo,
                Valor = indice < linha.Count ? linha[indice] : string.Empty,
            })
            .ToDictionary(par => par.Titulo, par => par.Valor));

        await File.WriteAllTextAsync(
            caminho,
            System.Text.Json.JsonSerializer.Serialize(
                registros, new System.Text.Json.JsonSerializerOptions { WriteIndented = true }),
            new UTF8Encoding(false),
            cancelamento);
    }

    /// <summary>Protege o separador, as aspas e a quebra de linha dentro da celula.</summary>
    private static string Escapar(string valor)
    {
        var texto = valor ?? string.Empty;
        return texto.Contains(';') || texto.Contains('"') || texto.Contains('\n')
            ? $"\"{texto.Replace("\"", "\"\"", StringComparison.Ordinal)}\""
            : texto;
    }
}
