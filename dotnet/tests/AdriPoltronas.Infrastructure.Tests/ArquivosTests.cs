using AdriPoltronas.Application.Dtos;
using AdriPoltronas.Infrastructure.Arquivos;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace AdriPoltronas.Infrastructure.Tests;

/// <summary>
/// Exportacao e importacao de planilhas.
/// </summary>
/// <remarks>
/// Escreve arquivo de verdade em pasta temporaria: o que importa aqui e
/// justamente o formato do arquivo que o operador vai abrir no Excel, e um
/// dublê de sistema de arquivos nao provaria nada sobre isso.
/// </remarks>
public sealed class ArquivosTests : IDisposable
{
    private readonly string _pasta = Path.Combine(
        Path.GetTempPath(), $"adri-arquivos-{Guid.NewGuid():N}");

    public ArquivosTests() => Directory.CreateDirectory(_pasta);

    private static ExportadorDePlanilha Exportador() =>
        new(NullLogger<ExportadorDePlanilha>.Instance);

    private static ImportadorDePlanilha Importador() =>
        new(NullLogger<ImportadorDePlanilha>.Instance);

    [Fact]
    public async Task CsvSaiComBomParaOExcelAbrirComAcento()
    {
        var caminho = Path.Combine(_pasta, "clientes.csv");

        await Exportador().ExportarAsync(
            caminho, FormatoDeArquivo.Csv, "Clientes", ["Nome"], [new[] { "Joao Coracao" }]);

        var bytes = await File.ReadAllBytesAsync(caminho);
        Assert.Equal([0xEF, 0xBB, 0xBF], bytes[..3]);
        Assert.Contains("Coracao", await File.ReadAllTextAsync(caminho), StringComparison.Ordinal);
    }

    [Fact]
    public async Task CelulaComPontoEVirgulaSaiEntreAspas()
    {
        var caminho = Path.Combine(_pasta, "escapado.csv");

        await Exportador().ExportarAsync(
            caminho, FormatoDeArquivo.Csv, "Clientes", ["Obs"],
            [new[] { "Entregar; cobrar depois" }]);

        var texto = await File.ReadAllTextAsync(caminho);
        Assert.Contains("\"Entregar; cobrar depois\"", texto, StringComparison.Ordinal);
    }

    [Fact]
    public async Task ArquivoAbertoDevolveMensagemUtilEmVezDeExcecao()
    {
        var caminho = Path.Combine(_pasta, "travado.csv");
        await File.WriteAllTextAsync(caminho, "x");

        using var trava = new FileStream(
            caminho, FileMode.Open, FileAccess.ReadWrite, FileShare.None);

        var resultado = await Exportador().ExportarAsync(
            caminho, FormatoDeArquivo.Csv, "Clientes", ["Nome"], [new[] { "Ana" }]);

        Assert.False(resultado.Sucesso);
        Assert.Contains("Feche", resultado.Mensagem, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task XlsxExportadoVoltaPelaImportacao()
    {
        var caminho = Path.Combine(_pasta, "ida-e-volta.xlsx");

        await Exportador().ExportarAsync(
            caminho, FormatoDeArquivo.Xlsx, "Clientes",
            ["Nome", "CEP", "Cidade", "Tipo"],
            [new[] { "Ana Souza", "89230-210", "Joinville", "Entrega" }]);

        var lidas = await Importador().LerAsync(caminho);

        Assert.True(lidas.Sucesso);
        var linha = Assert.Single(lidas.Valor!);
        Assert.Equal("Ana Souza", linha.Dados.Nome);
        Assert.Equal("Joinville", linha.Dados.Cidade);
    }

    [Fact]
    public async Task CabecalhoComAcentoEOrdemTrocadaEReconhecido()
    {
        // Planilha de outro sistema quase nunca chega na ordem que esperamos.
        var caminho = Path.Combine(_pasta, "fora-de-ordem.csv");
        await File.WriteAllTextAsync(
            caminho, "Município;Endereço;Cliente\nJoinville;Rua A;Ana Souza\n");

        var lidas = await Importador().LerAsync(caminho);

        var linha = Assert.Single(lidas.Valor!);
        Assert.Equal("Ana Souza", linha.Dados.Nome);
        Assert.Equal("Joinville", linha.Dados.Cidade);
        Assert.Equal("Rua A", linha.Dados.Rua);
    }

    [Fact]
    public async Task ONumeroDaLinhaApontaParaAPlanilha()
    {
        var caminho = Path.Combine(_pasta, "linhas.csv");
        await File.WriteAllTextAsync(caminho, "Nome\nAna\nBruno\n");

        var lidas = await Importador().LerAsync(caminho);

        Assert.Equal([2, 3], lidas.Valor!.Select(l => l.Numero));
    }

    [Fact]
    public async Task ArquivoInexistenteInformaEmVezDeEstourar()
    {
        var lidas = await Importador().LerAsync(Path.Combine(_pasta, "nao-existe.csv"));

        Assert.False(lidas.Sucesso);
    }

    public void Dispose()
    {
        if (Directory.Exists(_pasta))
        {
            Directory.Delete(_pasta, recursive: true);
        }
    }
}
