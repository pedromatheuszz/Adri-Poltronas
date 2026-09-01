using System.Collections.ObjectModel;
using AdriPoltronas.Application.Common;
using AdriPoltronas.Application.Dtos;
using AdriPoltronas.Application.UseCases.Clientes;
using AdriPoltronas.Application.UseCases.Dados;
using AdriPoltronas.Desktop.Navigation;
using AdriPoltronas.Desktop.Servicos;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using Microsoft.Extensions.Logging;

namespace AdriPoltronas.Desktop.ViewModels;

/// <summary>
/// Tela de clientes: lista, busca e o CRUD.
/// </summary>
/// <remarks>
/// Nao ha SQL, <c>DbContext</c> nem regra de cadastro aqui. O ViewModel expoe
/// estado, dispara comandos e reage ao <see cref="Resultado"/> que o caso de
/// uso devolve.
/// </remarks>
public sealed partial class ClientesViewModel(
    ExecutorDeCasosDeUso casos,
    IDialogos dialogos,
    IDespachante despachante,
    ILogger<ClientesViewModel> log) : ViewModelBase, IAtalhosDeTela
{
    /// <summary>Espera antes de consultar, para nao buscar a cada tecla.</summary>
    public static readonly TimeSpan AtrasoDaBusca = TimeSpan.FromMilliseconds(300);

    private CancellationTokenSource? _buscaPendente;

    public ObservableCollection<ClienteDto> Clientes { get; } = [];

    [ObservableProperty]
    private ClienteDto? _selecionado;

    [ObservableProperty]
    private string _termoDeBusca = string.Empty;

    /// <summary>Filtro de tipo da lista. O vazio corresponde a "todos".</summary>
    [ObservableProperty]
    private string _filtroDeTipo = "Todos";

    public IReadOnlyList<string> TiposDisponiveis { get; } = ["Todos", "Entrega", "Retirada"];

    public bool ListaVazia => Clientes.Count == 0;

    IRelayCommand? IAtalhosDeTela.ComandoNovo => NovoCommand;

    IRelayCommand? IAtalhosDeTela.ComandoAtualizar => RecarregarCommand;

    public override void AoEntrar() => RecarregarCommand.Execute(null);

    /// <summary>
    /// Reage ao texto digitado, adiando a consulta.
    /// </summary>
    /// <remarks>
    /// Gerado pelo CommunityToolkit a partir de <c>TermoDeBusca</c>. Sem o
    /// adiamento, cada letra dispararia uma consulta e as respostas poderiam
    /// chegar fora de ordem, deixando na tela o resultado de um termo antigo.
    /// </remarks>
    partial void OnTermoDeBuscaChanged(string value)
    {
        _buscaPendente?.Cancel();
        _buscaPendente = new CancellationTokenSource();
        var token = _buscaPendente.Token;

        _ = Task.Run(async () =>
        {
            try
            {
                await Task.Delay(AtrasoDaBusca, token);
                await ExecutarAsync(
                    () => CarregarAsync(token), "Nao foi possivel carregar os clientes.");
            }
            catch (OperationCanceledException)
            {
                // Outra tecla chegou antes: esta busca foi descartada.
            }
        }, token);
    }

    [RelayCommand]
    private Task RecarregarAsync() => ExecutarAsync(
        () => CarregarAsync(CancellationToken.None), "Nao foi possivel carregar os clientes.");

    [RelayCommand]
    private Task NovoAsync() => ExecutarAsync(async () =>
    {
        var dados = await dialogos.EditarClienteAsync(null);
        if (dados is null)
        {
            return;
        }

        var resultado = await casos.ExecutarAsync<CriarCliente, Resultado<ClienteDto>>(
            caso => caso.ExecutarAsync(dados));

        if (!resultado.Sucesso)
        {
            // Erro de validacao volta como texto para a barra de status; nao e
            // excecao, e nao vai para o log de falhas.
            Mensagem = resultado.Mensagem;
            return;
        }

        Mensagem = $"Cliente \"{resultado.Valor!.Nome}\" cadastrado.";
        await CarregarAsync(CancellationToken.None);
    }, "Nao foi possivel cadastrar o cliente.");

    [RelayCommand]
    private Task EditarAsync() => ExecutarAsync(async () =>
    {
        if (Selecionado is null)
        {
            Mensagem = "Selecione um cliente.";
            return;
        }

        var dados = await dialogos.EditarClienteAsync(Selecionado);
        if (dados is null)
        {
            return;
        }

        var resultado = await casos.ExecutarAsync<AtualizarCliente, Resultado<ClienteDto>>(
            caso => caso.ExecutarAsync(Selecionado.Id, dados));

        if (resultado.Falha == TipoDeFalha.NaoEncontrado)
        {
            // A lista da tela esta velha: recarregar e a resposta certa.
            Mensagem = resultado.Mensagem;
            await CarregarAsync(CancellationToken.None);
            return;
        }

        if (!resultado.Sucesso)
        {
            Mensagem = resultado.Mensagem;
            return;
        }

        Mensagem = "Cliente atualizado.";
        await CarregarAsync(CancellationToken.None);
    }, "Nao foi possivel atualizar o cliente.");

    [RelayCommand]
    private Task ExcluirAsync() => ExecutarAsync(async () =>
    {
        if (Selecionado is null)
        {
            Mensagem = "Selecione um cliente.";
            return;
        }

        var confirmado = await dialogos.ConfirmarAsync(
            "Excluir cliente",
            $"Excluir \"{Selecionado.Nome}\"? A acao nao pode ser desfeita.");
        if (!confirmado)
        {
            return;
        }

        var resultado = await casos.ExecutarAsync<ExcluirCliente, Resultado>(
            caso => caso.ExecutarAsync(Selecionado.Id));

        Mensagem = resultado.Sucesso ? "Cliente excluido." : resultado.Mensagem;
        await CarregarAsync(CancellationToken.None);
    }, "Nao foi possivel excluir o cliente.");

    [RelayCommand]
    private Task ImportarAsync() => ExecutarAsync(async () =>
    {
        var caminho = await dialogos.EscolherArquivoParaAbrirAsync("Importar clientes");
        if (string.IsNullOrWhiteSpace(caminho))
        {
            return;
        }

        var resultado = await casos.ExecutarAsync<
            ImportarClientes, Resultado<ResultadoDaImportacao>>(
            caso => caso.ExecutarAsync(caminho));

        if (!resultado.Sucesso || resultado.Valor is null)
        {
            Mensagem = resultado.Mensagem;
            return;
        }

        var importacao = resultado.Valor;
        Mensagem = importacao.Rejeitadas.Count == 0
            ? $"{importacao.Importados} clientes importados."
            : $"{importacao.Importados} importados, {importacao.Rejeitadas.Count} recusados " +
              $"(primeiro problema: linha {importacao.Rejeitadas[0].Numero}, " +
              $"{importacao.Rejeitadas[0].Motivo})";

        await CarregarAsync(CancellationToken.None);
    }, "Nao foi possivel importar o arquivo.");

    [RelayCommand]
    private Task ExportarAsync() => ExecutarAsync(async () =>
    {
        var caminho = await dialogos.EscolherArquivoParaSalvarAsync(
            "Exportar clientes", "clientes.xlsx", FormatoDeArquivo.Xlsx);
        if (string.IsNullOrWhiteSpace(caminho))
        {
            return;
        }

        var formato = caminho.EndsWith(".csv", StringComparison.OrdinalIgnoreCase)
            ? FormatoDeArquivo.Csv
            : FormatoDeArquivo.Xlsx;

        var resultado = await casos.ExecutarAsync<ExportarClientes, Resultado>(
            caso => caso.ExecutarAsync(caminho, formato));

        Mensagem = resultado.Sucesso ? $"Clientes exportados para {caminho}." : resultado.Mensagem;
    }, "Nao foi possivel exportar os clientes.");

    [RelayCommand]
    private Task BackupAsync() => ExecutarAsync(async () =>
    {
        var caminho = await dialogos.EscolherArquivoParaSalvarAsync(
            "Copia de seguranca",
            $"backup-{DateTime.Now:yyyy-MM-dd}.json",
            FormatoDeArquivo.Json);
        if (string.IsNullOrWhiteSpace(caminho))
        {
            return;
        }

        // Extensao decide o formato: .db pede a copia fiel do banco, qualquer
        // outra coisa gera o JSON legivel.
        var ehBanco = caminho.EndsWith(".db", StringComparison.OrdinalIgnoreCase);
        var resultado = await casos.ExecutarAsync<FazerBackup, Resultado<string>>(
            caso => ehBanco ? caso.BancoAsync(caminho) : caso.JsonAsync(caminho));

        Mensagem = resultado.Sucesso ? $"Backup gravado em {caminho}." : resultado.Mensagem;
    }, "Nao foi possivel gravar o backup.");

    partial void OnFiltroDeTipoChanged(string value) => RecarregarCommand.Execute(null);

    /// <summary>
    /// Recarrega a lista. NAO passa por <see cref="ViewModelBase.ExecutarAsync"/>.
    /// </summary>
    /// <remarks>
    /// Este metodo e chamado de dentro dos comandos, que ja rodam sob a guarda
    /// de reentrancia. Envolve-lo tambem fazia a guarda ver <c>Ocupado</c> e
    /// sair calada: o cliente era gravado no banco e a lista continuava sem
    /// ele, como se nada tivesse acontecido. Quem entra por fora (o comando
    /// Recarregar e a busca com atraso) e que aplica a guarda.
    /// </remarks>
    private async Task CarregarAsync(CancellationToken cancelamento)
    {
        var encontrados = await casos.ExecutarAsync<BuscarClientes, IReadOnlyList<ClienteDto>>(
            caso => caso.ExecutarAsync(TermoDeBusca, cancelamento));

        // O filtro de tipo e aplicado aqui, e nao no caso de uso: sao dois
        // valores fixos sobre uma lista ja carregada, e uma ida a mais ao banco
        // a cada clique nao compraria nada.
        if (FiltroDeTipo != "Todos")
        {
            encontrados = [.. encontrados.Where(c => c.Tipo == FiltroDeTipo)];
        }

        if (cancelamento.IsCancellationRequested)
        {
            return;
        }

        await despachante.NaInterfaceAsync(() =>
        {
            var idSelecionado = Selecionado?.Id;
            Clientes.Clear();
            foreach (var cliente in encontrados)
            {
                Clientes.Add(cliente);
            }

            // Manter a selecao evita que a linha "pule" depois de editar.
            Selecionado = Clientes.FirstOrDefault(c => c.Id == idSelecionado);
            OnPropertyChanged(nameof(ListaVazia));
        });
    }

    protected override void RegistrarFalha(Exception erro, string contexto) =>
        log.LogError(erro, "Falha na tela de clientes: {Contexto}", contexto);
}
