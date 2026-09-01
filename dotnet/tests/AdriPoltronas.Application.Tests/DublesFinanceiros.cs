using AdriPoltronas.Application.Abstractions;
using AdriPoltronas.Application.Common;
using AdriPoltronas.Application.Dtos;
using AdriPoltronas.Domain.Entities;
using AdriPoltronas.Domain.Enums;

namespace AdriPoltronas.Application.Tests;

/// <summary>Cobrancas em memoria.</summary>
public sealed class RepositorioFalsoDePagamentos : IPagamentoRepository
{
    private readonly List<Pagamento> _pagamentos = [];
    private int _proximoId = 1;

    public List<Pagamento> Adicionados { get; } = [];
    public List<Pagamento> Removidos { get; } = [];

    public Pagamento Semear(Pagamento pagamento)
    {
        DefinirId(pagamento, _proximoId++);
        _pagamentos.Add(pagamento);
        return pagamento;
    }

    public Task<IReadOnlyList<Pagamento>> BuscarAsync(
        FiltroDePagamentos filtro, CancellationToken cancelamento = default)
    {
        IEnumerable<Pagamento> encontrados = _pagamentos;

        if (!string.IsNullOrWhiteSpace(filtro.Cliente))
        {
            encontrados = encontrados.Where(p => p.ClienteNome.Contains(
                filtro.Cliente, StringComparison.OrdinalIgnoreCase));
        }

        if (StatusPagamentoExtensions.TentarConverter(filtro.Status, out var status))
        {
            encontrados = encontrados.Where(p => p.Status == status);
        }

        return Task.FromResult<IReadOnlyList<Pagamento>>([.. encontrados]);
    }

    public Task<Pagamento?> ObterPorIdAsync(int id, CancellationToken cancelamento = default) =>
        Task.FromResult(_pagamentos.FirstOrDefault(p => p.Id == id));

    public Task<IReadOnlyList<Pagamento>> AVencerAteAsync(
        DateTime limite, CancellationToken cancelamento = default) =>
        Task.FromResult<IReadOnlyList<Pagamento>>(
            [.. _pagamentos.Where(p =>
                p.Status is StatusPagamento.Pendente or StatusPagamento.Atrasado &&
                p.DataVencimento.DiasAte(limite) is <= 0)]);

    public void Adicionar(Pagamento pagamento)
    {
        Adicionados.Add(pagamento);
        Semear(pagamento);
    }

    public void Remover(Pagamento pagamento)
    {
        Removidos.Add(pagamento);
        _pagamentos.Remove(pagamento);
    }

    public Task<MetricasPagamentosDto> ObterMetricasAsync(
        CancellationToken cancelamento = default)
    {
        var recebidos = _pagamentos.Where(p => p.Status == StatusPagamento.Recebido).ToList();
        var abertos = _pagamentos
            .Where(p => p.Status is StatusPagamento.Pendente or StatusPagamento.Atrasado)
            .ToList();

        return Task.FromResult(new MetricasPagamentosDto(
            recebidos.Sum(p => p.Valor.Valor),
            abertos.Sum(p => p.Valor.Valor),
            0,
            recebidos.Count,
            abertos.Count));
    }

    private static void DefinirId(Pagamento pagamento, int id) =>
        typeof(Pagamento).GetProperty(nameof(Pagamento.Id))!.SetValue(pagamento, id);
}

/// <summary>Entregas em memoria.</summary>
public sealed class RepositorioFalsoDeEntregas : IEntregaRepository
{
    private readonly List<EntregaAgendada> _entregas = [];
    private int _proximoId = 1;

    public EntregaAgendada Semear(EntregaAgendada entrega)
    {
        typeof(EntregaAgendada).GetProperty(nameof(EntregaAgendada.Id))!
            .SetValue(entrega, _proximoId++);
        _entregas.Add(entrega);
        return entrega;
    }

    public Task<IReadOnlyList<EntregaAgendada>> BuscarAsync(
        string? status, CancellationToken cancelamento = default) =>
        Task.FromResult<IReadOnlyList<EntregaAgendada>>(
            StatusEntregaExtensions.TentarConverter(status, out var situacao)
                ? [.. _entregas.Where(e => e.Status == situacao)]
                : _entregas);

    public Task<EntregaAgendada?> ObterPorIdAsync(
        int id, CancellationToken cancelamento = default) =>
        Task.FromResult(_entregas.FirstOrDefault(e => e.Id == id));

    public Task<IReadOnlyList<EntregaAgendada>> PendentesAteAsync(
        DateTime limite, CancellationToken cancelamento = default) =>
        Task.FromResult<IReadOnlyList<EntregaAgendada>>(
            [.. _entregas.Where(e =>
                e.Status == StatusEntrega.Pendente && e.DataEntrega.DiasAte(limite) is <= 0)]);

    public void Adicionar(EntregaAgendada entrega) => Semear(entrega);

    public void Remover(EntregaAgendada entrega) => _entregas.Remove(entrega);
}

/// <summary>Chaves lidas em memoria.</summary>
public sealed class RepositorioFalsoDeNotificacoesLidas : INotificacaoLidaRepository
{
    private readonly HashSet<string> _chaves = new(StringComparer.Ordinal);

    public Task<IReadOnlySet<string>> ChavesLidasAsync(
        CancellationToken cancelamento = default) =>
        Task.FromResult<IReadOnlySet<string>>(_chaves);

    public Task MarcarComoLidasAsync(
        IReadOnlyCollection<string> chaves, CancellationToken cancelamento = default)
    {
        foreach (var chave in chaves)
        {
            _chaves.Add(chave);
        }

        return Task.CompletedTask;
    }

    public Task LimparAsync(CancellationToken cancelamento = default)
    {
        _chaves.Clear();
        return Task.CompletedTask;
    }
}

/// <summary>Provedor de cobranca que nunca sai da maquina.</summary>
public sealed class CobrancaFalsa : IServicoDeCobranca
{
    public bool Configurado { get; set; } = true;

    public int Emissoes { get; private set; }

    public Task<Resultado<DadosDaCobranca>> EmitirAsync(
        Pagamento pagamento, CancellationToken cancelamento = default)
    {
        Emissoes++;
        return Task.FromResult(Resultado<DadosDaCobranca>.Ok(
            new DadosDaCobranca("pay_1", "000201PIX", "imagem", string.Empty, string.Empty)));
    }

    public Task<Resultado> CancelarAsync(
        string cobrancaId, CancellationToken cancelamento = default) =>
        Task.FromResult(Resultado.Ok());
}
