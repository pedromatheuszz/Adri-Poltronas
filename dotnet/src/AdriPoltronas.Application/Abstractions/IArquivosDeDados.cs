using AdriPoltronas.Application.Common;
using AdriPoltronas.Application.Dtos;

namespace AdriPoltronas.Application.Abstractions;

/// <summary>Gravacao de listas em planilha ou texto.</summary>
public interface IExportadorDePlanilha
{
    /// <summary>Grava as linhas no caminho indicado, no formato pedido.</summary>
    Task<Resultado> ExportarAsync(
        string caminho,
        FormatoDeArquivo formato,
        string titulo,
        IReadOnlyList<string> cabecalhos,
        IReadOnlyList<IReadOnlyList<string>> linhas,
        CancellationToken cancelamento = default);
}

/// <summary>Leitura de cadastros vindos de arquivo.</summary>
public interface IImportadorDePlanilha
{
    /// <summary>
    /// Le o arquivo e devolve uma entrada por linha, junto do numero da linha.
    /// </summary>
    /// <remarks>
    /// Devolve dados crus, sem validar: quem valida e o Domain, com as mesmas
    /// regras do cadastro manual. Duas validacoes separadas divergiriam.
    /// </remarks>
    Task<Resultado<IReadOnlyList<LinhaImportada>>> LerAsync(
        string caminho, CancellationToken cancelamento = default);
}

/// <summary>Uma linha lida do arquivo, ainda sem validacao.</summary>
public sealed record LinhaImportada(int Numero, DadosDoCliente Dados);

/// <summary>Copia de seguranca do banco.</summary>
public interface IServicoDeBackup
{
    /// <summary>Copia fiel do arquivo do banco.</summary>
    Task<Resultado<string>> CopiarBancoAsync(
        string caminhoDestino, CancellationToken cancelamento = default);

    /// <summary>Despejo em JSON, legivel e independente do formato do banco.</summary>
    Task<Resultado<string>> ExportarJsonAsync(
        string caminhoDestino, CancellationToken cancelamento = default);
}
