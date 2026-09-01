using AdriPoltronas.Application.Abstractions;
using AdriPoltronas.Application.Common;
using AdriPoltronas.Application.Dtos;
using AdriPoltronas.Domain.Enums;
using Microsoft.Extensions.Logging;

namespace AdriPoltronas.Application.UseCases.Dados;

/// <summary>Grava o cadastro completo em planilha.</summary>
public sealed class ExportarClientes(
    IClienteRepository clientes,
    IExportadorDePlanilha exportador,
    ILogger<ExportarClientes> log)
{
    private static readonly string[] Cabecalhos =
        ["Id", "Nome", "CEP", "Rua", "Bairro", "Cidade", "Tipo", "Observacoes"];

    public async Task<Resultado> ExecutarAsync(
        string caminho, FormatoDeArquivo formato, CancellationToken cancelamento = default)
    {
        var cadastrados = await clientes.BuscarAsync(null, cancelamento);
        if (cadastrados.Count == 0)
        {
            return Resultado.Invalido(["Nao ha clientes para exportar."]);
        }

        var linhas = cadastrados
            .Select(c => (IReadOnlyList<string>)new[]
            {
                c.Id.ToString(),
                c.Nome,
                c.Endereco.Cep.Valor,
                c.Endereco.Rua,
                c.Endereco.Bairro,
                c.Endereco.Cidade,
                c.Tipo.ParaTexto(),
                c.Observacoes,
            })
            .ToList();

        var gravacao = await exportador.ExportarAsync(
            caminho, formato, "Clientes", Cabecalhos, linhas, cancelamento);

        if (gravacao.Sucesso)
        {
            log.LogInformation(
                "{Total} clientes exportados para {Caminho}.", cadastrados.Count, caminho);
        }

        return gravacao;
    }
}
