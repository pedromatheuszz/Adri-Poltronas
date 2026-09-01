using AdriPoltronas.Application.Abstractions;
using AdriPoltronas.Application.Dtos;
using AdriPoltronas.Domain.Entities;
using AdriPoltronas.Domain.Enums;
using Microsoft.EntityFrameworkCore;

namespace AdriPoltronas.Infrastructure.Persistence.Repositories;

/// <inheritdoc cref="IClienteRepository"/>
public sealed class ClienteRepository(AdriPoltronasDbContext contexto) : IClienteRepository
{
    public async Task<IReadOnlyList<Cliente>> BuscarAsync(
        string? termo, CancellationToken cancelamento = default)
    {
        var consulta = contexto.Clientes.AsQueryable();

        var procurado = termo?.Trim();
        if (!string.IsNullOrEmpty(procurado))
        {
            // EF.Functions.Like vira LIKE no SQL, com o termo como parametro.
            // Interpolar o texto na consulta seria injecao; e o LIKE do SQLite
            // ja e insensivel a caixa para ASCII, como a busca antiga.
            var padrao = $"%{procurado}%";
            consulta = consulta.Where(c =>
                EF.Functions.Like(c.Nome, padrao) ||
                EF.Functions.Like(c.Endereco.Cidade, padrao) ||
                EF.Functions.Like(c.Endereco.Bairro, padrao));
        }

        // Mais recentes primeiro: e a ordem que a lista sempre teve, e o que o
        // operador espera depois de cadastrar alguem.
        return await consulta
            .OrderByDescending(c => c.Id)
            .AsNoTracking()
            .ToListAsync(cancelamento);
    }

    public Task<Cliente?> ObterPorIdAsync(int id, CancellationToken cancelamento = default) =>
        // Com rastreamento: quem chama isto vai alterar a entidade, e o
        // rastreamento e o que faz o UPDATE sair sozinho no ConfirmarAsync.
        contexto.Clientes.FirstOrDefaultAsync(c => c.Id == id, cancelamento);

    public void Adicionar(Cliente cliente) => contexto.Clientes.Add(cliente);

    public void Remover(Cliente cliente) => contexto.Clientes.Remove(cliente);

    public async Task<MetricasDashboardDto> ObterMetricasAsync(
        DateTime inicioDaJanela, CancellationToken cancelamento = default)
    {
        // Uma consulta so, agrupando no banco: quatro COUNT separados fariam
        // quatro varreduras da mesma tabela.
        var resumo = await contexto.Clientes
            .GroupBy(_ => 1)
            .Select(grupo => new
            {
                Total = grupo.Count(),
                Entrega = grupo.Count(c => c.Tipo == TipoAtendimento.Entrega),
                Retirada = grupo.Count(c => c.Tipo == TipoAtendimento.Retirada),
                Recentes = grupo.Count(c => c.CriadoEm >= inicioDaJanela),
            })
            .FirstOrDefaultAsync(cancelamento);

        return resumo is null
            // Base vazia: o GroupBy nao devolve linha nenhuma.
            ? MetricasDashboardDto.Vazio
            : new MetricasDashboardDto(resumo.Total, resumo.Entrega, resumo.Retirada, resumo.Recentes);
    }
}
