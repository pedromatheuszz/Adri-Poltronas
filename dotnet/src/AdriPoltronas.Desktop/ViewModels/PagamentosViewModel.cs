using System.Collections.ObjectModel;
using AdriPoltronas.Application.Common;
using AdriPoltronas.Application.Dtos;
using AdriPoltronas.Application.UseCases.Clientes;
using AdriPoltronas.Application.UseCases.Pagamentos;
using AdriPoltronas.Desktop.Navigation;
using AdriPoltronas.Desktop.Servicos;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using Microsoft.Extensions.Logging;

namespace AdriPoltronas.Desktop.ViewModels;

/// <summary>Aba financeira: lancamentos, filtros e totais.</summary>
public sealed partial class PagamentosViewModel(
    ExecutorDeCasosDeUso casos,
    IDialogos dialogos,
    IDespachante despachante,
    ILogger<PagamentosViewModel> log) : ViewModelBase, IAtalhosDeTela
{
    /// <summary>Opcoes do filtro. O vazio corresponde a "todos".</summary>
    public IReadOnlyList<string> StatusDisponiveis { get; } =
        ["Todos", "Pendente", "Recebido", "Atrasado", "Cancelado"];

    public ObservableCollection<PagamentoDto> Pagamentos { get; } = [];

    [ObservableProperty]
    private PagamentoDto? _selecionado;

    [ObservableProperty]
    private string _filtroDeCliente = string.Empty;

    [ObservableProperty]
    private string _filtroDeStatus = "Todos";

    [ObservableProperty]
    private MetricasPagamentosDto _metricas = MetricasPagamentosDto.Vazio;

    public bool ListaVazia => Pagamentos.Count == 0;

    IRelayCommand? IAtalhosDeTela.ComandoNovo => NovoCommand;

    IRelayCommand? IAtalhosDeTela.ComandoAtualizar => RecarregarCommand;

    public override void AoEntrar() => RecarregarCommand.Execute(null);

    [RelayCommand]
    private Task RecarregarAsync() => ExecutarAsync(
        CarregarAsync, "Nao foi possivel carregar os pagamentos.");

    [RelayCommand]
    private Task NovoAsync() => ExecutarAsync(async () =>
    {
        // A lista de clientes vem daqui, e nao de dentro do dialogo: janela
        // nao chama caso de uso.
        var clientes = await casos.ExecutarAsync<BuscarClientes, IReadOnlyList<ClienteDto>>(
            caso => caso.ExecutarAsync(null));
        if (clientes.Count == 0)
        {
            Mensagem = "Cadastre um cliente antes de lancar uma cobranca.";
            return;
        }

        var dados = await dialogos.NovoPagamentoAsync(clientes);
        if (dados is null)
        {
            return;
        }

        var resultado = await casos.ExecutarAsync<RegistrarPagamento, Resultado<PagamentoDto>>(
            caso => caso.ExecutarAsync(dados));

        if (!resultado.Sucesso)
        {
            Mensagem = resultado.Mensagem;
            return;
        }

        Mensagem = $"Lancamento de {resultado.Valor!.ValorFormatado} registrado.";
        await CarregarAsync();
    }, "Nao foi possivel registrar o lancamento.");

    [RelayCommand]
    private Task ConfirmarAsync() => ExecutarAsync(async () =>
    {
        if (!ExigirSelecao())
        {
            return;
        }

        var resultado = await casos.ExecutarAsync<ConfirmarPagamento, Resultado<PagamentoDto>>(
            caso => caso.ExecutarAsync(Selecionado!.Id));

        Mensagem = resultado.Sucesso ? "Recebimento confirmado." : resultado.Mensagem;
        await CarregarAsync();
    }, "Nao foi possivel confirmar o recebimento.");

    [RelayCommand]
    private Task CancelarAsync() => ExecutarAsync(async () =>
    {
        if (!ExigirSelecao())
        {
            return;
        }

        var resultado = await casos.ExecutarAsync<CancelarPagamento, Resultado<PagamentoDto>>(
            caso => caso.ExecutarAsync(Selecionado!.Id));

        Mensagem = resultado.Sucesso ? "Cobranca cancelada." : resultado.Mensagem;
        await CarregarAsync();
    }, "Nao foi possivel cancelar a cobranca.");

    [RelayCommand]
    private Task ExcluirAsync() => ExecutarAsync(async () =>
    {
        if (!ExigirSelecao())
        {
            return;
        }

        var confirmado = await dialogos.ConfirmarAsync(
            "Excluir lancamento",
            $"Excluir o lancamento de {Selecionado!.ValorFormatado} de " +
            $"{Selecionado.ClienteNome}? A acao nao pode ser desfeita.");
        if (!confirmado)
        {
            return;
        }

        var resultado = await casos.ExecutarAsync<ExcluirPagamento, Resultado>(
            caso => caso.ExecutarAsync(Selecionado.Id));

        Mensagem = resultado.Sucesso ? "Lancamento excluido." : resultado.Mensagem;
        await CarregarAsync();
    }, "Nao foi possivel excluir o lancamento.");

    [RelayCommand]
    private Task GerarCobrancaAsync() => ExecutarAsync(async () =>
    {
        if (!ExigirSelecao())
        {
            return;
        }

        var resultado = await casos.ExecutarAsync<GerarCobranca, Resultado<PagamentoDto>>(
            caso => caso.ExecutarAsync(Selecionado!.Id));

        if (!resultado.Sucesso)
        {
            Mensagem = resultado.Mensagem;
            return;
        }

        await CarregarAsync();
        // A janela da cobranca abre depois de recarregar: mostra o codigo Pix
        // ja gravado, e nao um valor que ainda so existia em memoria.
        await dialogos.MostrarCobrancaAsync(resultado.Valor!);
        Mensagem = "Cobranca emitida.";
    }, "Nao foi possivel emitir a cobranca.");

    partial void OnFiltroDeClienteChanged(string value) => RecarregarCommand.Execute(null);

    partial void OnFiltroDeStatusChanged(string value) => RecarregarCommand.Execute(null);

    /// <summary>
    /// Recarrega lista e totais. NAO passa por <see cref="ViewModelBase.ExecutarAsync"/>.
    /// </summary>
    /// <remarks>
    /// Chamado de dentro dos comandos, que ja seguram a guarda de reentrancia.
    /// Envolver de novo faria a guarda ver <c>Ocupado</c> e sair calada: o
    /// lancamento entraria no banco e a lista continuaria mostrando o estado
    /// anterior.
    /// </remarks>
    private async Task CarregarAsync()
    {
        var status = FiltroDeStatus == "Todos" ? null : FiltroDeStatus;
        var filtro = new FiltroDePagamentos(FiltroDeCliente, status);

        var encontrados = await casos.ExecutarAsync<BuscarPagamentos, IReadOnlyList<PagamentoDto>>(
            caso => caso.ExecutarAsync(filtro));
        var totais = await casos.ExecutarAsync<ObterMetricasPagamentos, MetricasPagamentosDto>(
            caso => caso.ExecutarAsync());

        await despachante.NaInterfaceAsync(() =>
        {
            var idSelecionado = Selecionado?.Id;
            Pagamentos.Clear();
            foreach (var pagamento in encontrados)
            {
                Pagamentos.Add(pagamento);
            }

            Selecionado = Pagamentos.FirstOrDefault(p => p.Id == idSelecionado);
            Metricas = totais;
            OnPropertyChanged(nameof(ListaVazia));
        });
    }

    private bool ExigirSelecao()
    {
        if (Selecionado is not null)
        {
            return true;
        }

        Mensagem = "Selecione um lancamento.";
        return false;
    }

    protected override void RegistrarFalha(Exception erro, string contexto) =>
        log.LogError(erro, "Falha na tela de pagamentos: {Contexto}", contexto);
}
