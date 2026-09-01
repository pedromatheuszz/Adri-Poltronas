using AdriPoltronas.Application.Abstractions;
using AdriPoltronas.Application.Dtos;
using AdriPoltronas.Desktop.Navigation;
using AdriPoltronas.Desktop.Servicos;
using AdriPoltronas.Domain.Entities;
using AdriPoltronas.Domain.Enums;

namespace AdriPoltronas.Desktop.Tests;

/// <summary>Cobrancas em memoria, para exercitar a aba financeira sem banco.</summary>
public sealed class PagamentosEmMemoria : IPagamentoRepository
{
    private readonly List<Pagamento> _pagamentos = [];
    private int _proximoId = 1;

    public Pagamento Semear(Pagamento pagamento)
    {
        typeof(Pagamento).GetProperty(nameof(Pagamento.Id))!
            .SetValue(pagamento, _proximoId++);
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

    public void Adicionar(Pagamento pagamento) => Semear(pagamento);

    public void Remover(Pagamento pagamento) => _pagamentos.Remove(pagamento);

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
}

/// <summary>Dialogos da aba financeira, com resposta programada.</summary>
public sealed class DialogosDePagamento : IDialogos
{
    public DadosDoPagamento? ProximoFormulario { get; set; }
    public bool Confirmacao { get; set; } = true;
    public bool PerguntouConfirmacao { get; private set; }
    public bool AbriuFormulario { get; private set; }
    public bool MostrouCobranca { get; private set; }

    public Task<DadosDoPagamento?> NovoPagamentoAsync(IReadOnlyList<ClienteDto> clientes)
    {
        AbriuFormulario = true;
        return Task.FromResult(ProximoFormulario);
    }

    public Task MostrarCobrancaAsync(PagamentoDto pagamento)
    {
        MostrouCobranca = true;
        return Task.CompletedTask;
    }

    public Task<bool> ConfirmarAsync(string titulo, string pergunta)
    {
        PerguntouConfirmacao = true;
        return Task.FromResult(Confirmacao);
    }

    public Task<DadosDoCliente?> EditarClienteAsync(ClienteDto? existente) =>
        Task.FromResult<DadosDoCliente?>(null);

    public Task<string?> EscolherArquivoParaSalvarAsync(
        string titulo, string nomeSugerido, FormatoDeArquivo formato) =>
        Task.FromResult<string?>(null);

    public Task<string?> EscolherArquivoParaAbrirAsync(string titulo) =>
        Task.FromResult<string?>(null);
}

public sealed class DespachanteSincrono : IDespachante
{
    public Task NaInterfaceAsync(Action acao)
    {
        acao();
        return Task.CompletedTask;
    }
}

public sealed class RelogioFixo : IRelogio
{
    public DateTime Agora => new(2026, 8, 28, 14, 30, 0);
}

public sealed class UnidadeSemEfeito : IUnidadeDeTrabalho
{
    public Task<int> ConfirmarAsync(CancellationToken cancelamento = default) =>
        Task.FromResult(0);
}

public sealed class HistoricoEmMemoria : IHistoricoRepository
{
    private readonly List<RegistroHistorico> _registros = [];

    public void Adicionar(RegistroHistorico registro) => _registros.Add(registro);

    public Task<IReadOnlyList<RegistroHistorico>> UltimosAsync(
        int quantidade, CancellationToken cancelamento = default) =>
        Task.FromResult<IReadOnlyList<RegistroHistorico>>(_registros);
}

public sealed class RepositorioEmMemoria : IClienteRepository
{
    private readonly List<Cliente> _clientes = [];
    private int _proximoId = 1;

    public void Semear(string nome, string bairro) => Semear(Cliente.Criar(
        nome, "89230-210", "Rua A", bairro, "Joinville", "Entrega", "",
        new DateTime(2026, 8, 28, 14, 30, 0)));

    public Cliente Semear(Cliente cliente)
    {
        Adicionar(cliente);
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
                c.Endereco.Bairro.Contains(procurado, StringComparison.OrdinalIgnoreCase))];
        return Task.FromResult(encontrados);
    }

    public Task<Cliente?> ObterPorIdAsync(int id, CancellationToken cancelamento = default) =>
        Task.FromResult(_clientes.FirstOrDefault(c => c.Id == id));

    public void Adicionar(Cliente cliente)
    {
        typeof(Cliente).GetProperty(nameof(Cliente.Id))!.SetValue(cliente, _proximoId++);
        _clientes.Add(cliente);
    }

    public void Remover(Cliente cliente) => _clientes.Remove(cliente);

    public Task<MetricasDashboardDto> ObterMetricasAsync(
        DateTime inicioDaJanela, CancellationToken cancelamento = default) =>
        Task.FromResult(new MetricasDashboardDto(
            _clientes.Count,
            _clientes.Count(c => c.Tipo == TipoAtendimento.Entrega),
            _clientes.Count(c => c.Tipo == TipoAtendimento.Retirada),
            _clientes.Count));
}

/// <summary>Entregas em memoria, para montar os alertas sem banco.</summary>
public sealed class EntregasEmMemoria : IEntregaRepository
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
        Task.FromResult<IReadOnlyList<EntregaAgendada>>(_entregas);

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
public sealed class LidasEmMemoria : INotificacaoLidaRepository
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
