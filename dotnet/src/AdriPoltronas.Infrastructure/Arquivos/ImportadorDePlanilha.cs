using System.Text;
using System.Text.Json;
using AdriPoltronas.Application.Abstractions;
using AdriPoltronas.Application.Common;
using AdriPoltronas.Application.Dtos;
using ClosedXML.Excel;
using Microsoft.Extensions.Logging;

namespace AdriPoltronas.Infrastructure.Arquivos;

/// <summary>
/// Le cadastros de CSV, XLSX ou JSON.
/// </summary>
/// <remarks>
/// As colunas sao reconhecidas pelo cabecalho, e nao pela posicao: planilha
/// exportada de outro sistema quase nunca traz a ordem que o nosso espera, e
/// exigir ordem fixa transformaria toda importacao em trabalho manual.
/// </remarks>
public sealed class ImportadorDePlanilha(ILogger<ImportadorDePlanilha> log)
    : IImportadorDePlanilha
{
    /// <summary>Nomes aceitos para cada campo, ja sem acento e em minusculas.</summary>
    private static readonly Dictionary<string, string[]> Sinonimos = new()
    {
        ["nome"] = ["nome", "cliente", "nome do cliente"],
        ["cep"] = ["cep", "codigo postal"],
        ["rua"] = ["rua", "endereco", "logradouro"],
        ["bairro"] = ["bairro"],
        ["cidade"] = ["cidade", "municipio", "localidade"],
        ["tipo"] = ["tipo", "entrega_retirada", "entrega/retirada", "entrega"],
        ["observacoes"] = ["observacoes", "obs", "observacao"],
    };

    public async Task<Resultado<IReadOnlyList<LinhaImportada>>> LerAsync(
        string caminho, CancellationToken cancelamento = default)
    {
        if (!File.Exists(caminho))
        {
            return Resultado<IReadOnlyList<LinhaImportada>>.NaoEncontrado(
                "Arquivo nao encontrado.");
        }

        try
        {
            var extensao = Path.GetExtension(caminho).ToLowerInvariant();
            var linhas = extensao switch
            {
                ".xlsx" => LerXlsx(caminho),
                ".json" => await LerJsonAsync(caminho, cancelamento),
                _ => await LerCsvAsync(caminho, cancelamento),
            };

            return Resultado<IReadOnlyList<LinhaImportada>>.Ok(linhas);
        }
        catch (Exception erro) when (erro is IOException or JsonException or FormatException)
        {
            log.LogWarning(erro, "Falha ao ler {Caminho}.", caminho);
            return Resultado<IReadOnlyList<LinhaImportada>>.Invalido(
                ["Nao foi possivel ler o arquivo. Confira o formato e tente de novo."]);
        }
    }

    private static IReadOnlyList<LinhaImportada> LerXlsx(string caminho)
    {
        using var planilha = new XLWorkbook(caminho);
        var aba = planilha.Worksheets.First();
        var usadas = aba.RangeUsed();
        if (usadas is null)
        {
            return [];
        }

        var todas = usadas.RowsUsed().ToList();
        if (todas.Count < 2)
        {
            return [];
        }

        var cabecalho = todas[0].Cells().Select(c => c.GetString()).ToList();
        var resultado = new List<LinhaImportada>(todas.Count - 1);

        for (var indice = 1; indice < todas.Count; indice++)
        {
            var valores = todas[indice].Cells().Select(c => c.GetString()).ToList();
            resultado.Add(new LinhaImportada(indice + 1, Montar(cabecalho, valores)));
        }

        return resultado;
    }

    private static async Task<IReadOnlyList<LinhaImportada>> LerCsvAsync(
        string caminho, CancellationToken cancelamento)
    {
        var conteudo = await File.ReadAllLinesAsync(caminho, Encoding.UTF8, cancelamento);
        if (conteudo.Length < 2)
        {
            return [];
        }

        // Separador detectado pelo cabecalho: planilha brasileira sai com ponto
        // e virgula, exportacao de sistema estrangeiro sai com virgula.
        var separador = conteudo[0].Count(c => c == ';') >= conteudo[0].Count(c => c == ',')
            ? ';'
            : ',';

        var cabecalho = Dividir(conteudo[0], separador);
        var resultado = new List<LinhaImportada>(conteudo.Length - 1);

        for (var indice = 1; indice < conteudo.Length; indice++)
        {
            if (string.IsNullOrWhiteSpace(conteudo[indice]))
            {
                continue;
            }

            resultado.Add(new LinhaImportada(
                indice + 1, Montar(cabecalho, Dividir(conteudo[indice], separador))));
        }

        return resultado;
    }

    private static async Task<IReadOnlyList<LinhaImportada>> LerJsonAsync(
        string caminho, CancellationToken cancelamento)
    {
        var texto = await File.ReadAllTextAsync(caminho, cancelamento);
        using var documento = JsonDocument.Parse(texto);

        var raiz = documento.RootElement;
        // Aceita tanto o array puro quanto o backup, que embrulha em "clientes".
        if (raiz.ValueKind == JsonValueKind.Object &&
            raiz.TryGetProperty("clientes", out var lista))
        {
            raiz = lista;
        }

        if (raiz.ValueKind != JsonValueKind.Array)
        {
            return [];
        }

        var resultado = new List<LinhaImportada>();
        var numero = 1;

        foreach (var item in raiz.EnumerateArray())
        {
            numero++;
            if (item.ValueKind != JsonValueKind.Object)
            {
                continue;
            }

            var campos = item.EnumerateObject()
                .ToDictionary(
                    p => Normalizar(p.Name),
                    p => p.Value.ValueKind == JsonValueKind.String
                        ? p.Value.GetString() ?? string.Empty
                        : p.Value.ToString(),
                    StringComparer.Ordinal);

            resultado.Add(new LinhaImportada(numero, Montar(campos)));
        }

        return resultado;
    }

    private static DadosDoCliente Montar(
        IReadOnlyList<string> cabecalho, IReadOnlyList<string> valores)
    {
        var campos = new Dictionary<string, string>(StringComparer.Ordinal);
        for (var coluna = 0; coluna < cabecalho.Count; coluna++)
        {
            campos[Normalizar(cabecalho[coluna])] =
                coluna < valores.Count ? valores[coluna].Trim() : string.Empty;
        }

        return Montar(campos);
    }

    private static DadosDoCliente Montar(IReadOnlyDictionary<string, string> campos) =>
        new(
            Campo(campos, "nome"),
            Campo(campos, "cep"),
            Campo(campos, "rua"),
            Campo(campos, "bairro"),
            Campo(campos, "cidade"),
            Campo(campos, "tipo"),
            Campo(campos, "observacoes"));

    private static string? Campo(IReadOnlyDictionary<string, string> campos, string alvo)
    {
        foreach (var nome in Sinonimos[alvo])
        {
            if (campos.TryGetValue(nome, out var valor) && !string.IsNullOrWhiteSpace(valor))
            {
                return valor.Trim();
            }
        }

        return null;
    }

    /// <summary>Divide respeitando aspas, que protegem o separador dentro da celula.</summary>
    private static List<string> Dividir(string linha, char separador)
    {
        var partes = new List<string>();
        var atual = new StringBuilder();
        var dentroDeAspas = false;

        foreach (var caractere in linha)
        {
            if (caractere == '"')
            {
                dentroDeAspas = !dentroDeAspas;
                continue;
            }

            if (caractere == separador && !dentroDeAspas)
            {
                partes.Add(atual.ToString().Trim());
                atual.Clear();
                continue;
            }

            atual.Append(caractere);
        }

        partes.Add(atual.ToString().Trim());
        return partes;
    }

    /// <summary>Minusculas e sem acento, para casar cabecalhos escritos de qualquer jeito.</summary>
    private static string Normalizar(string texto)
    {
        var decomposto = texto.Trim().ToLowerInvariant().Normalize(NormalizationForm.FormD);
        var limpo = new StringBuilder(decomposto.Length);

        foreach (var caractere in decomposto)
        {
            if (System.Globalization.CharUnicodeInfo.GetUnicodeCategory(caractere)
                != System.Globalization.UnicodeCategory.NonSpacingMark)
            {
                limpo.Append(caractere);
            }
        }

        return limpo.ToString().Normalize(NormalizationForm.FormC);
    }
}
