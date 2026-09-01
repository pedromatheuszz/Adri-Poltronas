using System.Data.Common;
using System.Text;
using System.Text.Json;
using AdriPoltronas.Application.Abstractions;
using AdriPoltronas.Application.Common;
using AdriPoltronas.Domain.Enums;
using AdriPoltronas.Infrastructure.Persistence;
using AdriPoltronas.Infrastructure.Sistema;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Logging;

namespace AdriPoltronas.Infrastructure.Arquivos;

/// <summary>Copia de seguranca do banco, em arquivo ou em JSON.</summary>
public sealed class ServicoDeBackup(
    AdriPoltronasDbContext contexto, ILogger<ServicoDeBackup> log) : IServicoDeBackup
{
    public async Task<Resultado<string>> CopiarBancoAsync(
        string caminhoDestino, CancellationToken cancelamento = default)
    {
        try
        {
            // VACUUM INTO produz um arquivo consistente mesmo com o banco
            // aberto. Copiar o arquivo com File.Copy enquanto ha escrita em
            // andamento pode gravar um estado partido pela metade.
            await contexto.Database.ExecuteSqlRawAsync(
                "VACUUM INTO {0}", [caminhoDestino], cancelamento);

            log.LogInformation("Backup do banco gravado em {Caminho}.", caminhoDestino);
            return Resultado<string>.Ok(caminhoDestino);
        }
        catch (Exception erro) when (erro is DbException or IOException or InvalidOperationException)
        {
            log.LogError(erro, "Falha ao copiar o banco para {Caminho}.", caminhoDestino);
            return Resultado<string>.Invalido(
                ["Nao foi possivel gravar a copia. Escolha outra pasta ou outro nome."]);
        }
    }

    public async Task<Resultado<string>> ExportarJsonAsync(
        string caminhoDestino, CancellationToken cancelamento = default)
    {
        try
        {
            var clientes = await contexto.Clientes.AsNoTracking().ToListAsync(cancelamento);
            var pagamentos = await contexto.Pagamentos.AsNoTracking().ToListAsync(cancelamento);
            var entregas = await contexto.Entregas.AsNoTracking().ToListAsync(cancelamento);

            var conteudo = new
            {
                gerado_em = DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss"),
                origem = PastaDeDados.CaminhoDoBanco(),
                clientes = clientes.Select(c => new
                {
                    c.Id,
                    c.Nome,
                    Cep = c.Endereco.Cep.Valor,
                    c.Endereco.Rua,
                    c.Endereco.Bairro,
                    c.Endereco.Cidade,
                    Tipo = c.Tipo.ParaTexto(),
                    c.Observacoes,
                    CriadoEm = c.CriadoEm.ToString("yyyy-MM-dd HH:mm:ss"),
                }),
                pagamentos = pagamentos.Select(p => new
                {
                    p.Id,
                    p.ClienteId,
                    p.ClienteNome,
                    Valor = p.Valor.Valor,
                    p.Descricao,
                    Status = p.Status.ParaTexto(),
                    Tipo = p.Tipo.ParaTexto(),
                    DataVencimento = p.DataVencimento.Texto,
                    DataPagamento = p.DataPagamento.Texto,
                }),
                entregas = entregas.Select(e => new
                {
                    e.Id,
                    e.ClienteId,
                    e.ClienteNome,
                    DataEntrega = e.DataEntrega.Texto,
                    e.HoraEntrega,
                    e.Descricao,
                    Status = e.Status.ParaTexto(),
                }),
            };

            var json = JsonSerializer.Serialize(
                conteudo, new JsonSerializerOptions { WriteIndented = true });

            await File.WriteAllTextAsync(
                caminhoDestino, json, new UTF8Encoding(false), cancelamento);

            log.LogInformation("Backup JSON gravado em {Caminho}.", caminhoDestino);
            return Resultado<string>.Ok(caminhoDestino);
        }
        catch (Exception erro) when (erro is IOException or UnauthorizedAccessException)
        {
            log.LogError(erro, "Falha ao gravar o backup JSON em {Caminho}.", caminhoDestino);
            return Resultado<string>.Invalido(
                ["Nao foi possivel gravar o arquivo. Escolha outra pasta ou outro nome."]);
        }
    }
}
