using AdriPoltronas.Application.Abstractions;
using AdriPoltronas.Application.Dtos;
using AdriPoltronas.Domain.Entities;
using AdriPoltronas.Domain.Enums;

namespace AdriPoltronas.Application.Tests;

/// <summary>
/// Repositorio em memoria.
/// </summary>
/// <remarks>
/// Escrito a mao em vez de gerado por uma biblioteca de mock: sao poucos
/// metodos, e um dublê de verdade deixa os testes lendo como codigo comum, sem
/// cadeia de <c>Setup(...).Returns(...)</c> para decifrar.
/// </remarks>
public sealed class RepositorioFalsoDeClientes : IClienteRepository
{
    private readonly List<Cliente> _clientes = [];
    private int _proximoId = 1;

    public List<Cliente> Adicionados { get; } = [];
    public List<Cliente> Removidos { get; } = [];

    public Cliente Semear(Cliente cliente)
    {
        DefinirId(cliente, _proximoId++);
        _clientes.Add(cliente);
        return cliente;
    }

    public Task<IReadOnlyList<Cliente>> BuscarAsync(
        string? termo, CancellationToken cancelamento = default)
    {
        var procurado = termo?.Trim();
        IReadOnlyList<Cliente> encontrados = string.IsNullOrEmpty(procurado)
            ? _clientes
            : [.. _clientes.Where(c =>
                c.Nome.Contains(procurado, StringComparison.OrdinalIgnoreCase) ||
                c.Endereco.Cidade.Contains(procurado, StringComparison.OrdinalIgnoreCase) ||
                c.Endereco.Bairro.Contains(procurado, StringComparison.OrdinalIgnoreCase))];
        return Task.FromResult(encontrados);
    }

    public Task<Cliente?> ObterPorIdAsync(int id, CancellationToken cancelamento = default) =>
        Task.FromResult(_clientes.FirstOrDefault(c => c.Id == id));

    public void Adicionar(Cliente cliente)
    {
        Adicionados.Add(cliente);
        Semear(cliente);
    }

    public void Remover(Cliente cliente)
    {
        Removidos.Add(cliente);
        _clientes.Remove(cliente);
    }

    public Task<MetricasDashboardDto> ObterMetricasAsync(
        DateTime inicioDaJanela, CancellationToken cancelamento = default) =>
        Task.FromResult(new MetricasDashboardDto(
            _clientes.Count,
            _clientes.Count(c => c.Tipo == TipoAtendimento.Entrega),
            _clientes.Count(c => c.Tipo == TipoAtendimento.Retirada),
            _clientes.Count(c => c.CriadoEm >= inicioDaJanela)));

    /// <summary>
    /// Atribui o id que o banco atribuiria.
    /// </summary>
    /// <remarks>
    /// A propriedade tem setter privado justamente para que so a persistencia
    /// defina o identificador. Aqui o dublê faz o papel dela, via reflexao --
    /// o preco de manter a entidade fechada para o resto do sistema.
    /// </remarks>
    private static void DefinirId(Cliente cliente, int id) =>
        typeof(Cliente).GetProperty(nameof(Cliente.Id))!.SetValue(cliente, id);
}

/// <summary>Historico em memoria: guarda o que foi registrado, para conferencia.</summary>
public sealed class RepositorioFalsoDeHistorico : IHistoricoRepository
{
    public List<RegistroHistorico> Registrados { get; } = [];

    public void Adicionar(RegistroHistorico registro) => Registrados.Add(registro);

    public Task<IReadOnlyList<RegistroHistorico>> UltimosAsync(
        int quantidade, CancellationToken cancelamento = default) =>
        Task.FromResult<IReadOnlyList<RegistroHistorico>>(
            [.. Registrados.OrderByDescending(r => r.DataHora).Take(quantidade)]);
}

/// <summary>Conta as confirmacoes, para provar que tudo entrou numa transacao so.</summary>
public sealed class UnidadeDeTrabalhoFalsa : IUnidadeDeTrabalho
{
    public int Confirmacoes { get; private set; }

    public Task<int> ConfirmarAsync(CancellationToken cancelamento = default)
    {
        Confirmacoes++;
        return Task.FromResult(0);
    }
}

/// <summary>Relogio parado, para o teste nao depender do dia em que roda.</summary>
public sealed class RelogioFalso(DateTime agora) : IRelogio
{
    public DateTime Agora { get; set; } = agora;
}
