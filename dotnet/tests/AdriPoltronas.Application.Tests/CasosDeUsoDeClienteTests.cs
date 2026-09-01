using AdriPoltronas.Application.Common;
using AdriPoltronas.Application.Dtos;
using AdriPoltronas.Application.UseCases.Clientes;
using AdriPoltronas.Application.UseCases.Dashboard;
using AdriPoltronas.Domain.Entities;
using AdriPoltronas.Domain.Enums;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace AdriPoltronas.Application.Tests;

/// <summary>
/// Casos de uso do cadastro, sem banco nenhum.
/// </summary>
/// <remarks>
/// Rodam contra dublês em memoria: e essa a razao pratica de
/// <c>IClienteRepository</c> existir. Com o EF Core no meio, cada um destes
/// testes precisaria de um arquivo temporario e levaria centenas de vezes mais
/// tempo para verificar a mesma decisao.
/// </remarks>
public sealed class CasosDeUsoDeClienteTests
{
    private static readonly DateTime Agora = new(2026, 8, 28, 14, 30, 0);

    private readonly RepositorioFalsoDeClientes _clientes = new();
    private readonly RepositorioFalsoDeHistorico _historico = new();
    private readonly UnidadeDeTrabalhoFalsa _unidade = new();
    private readonly RelogioFalso _relogio = new(Agora);

    private static DadosDoCliente DadosValidos(string nome = "Ana Paula", string tipo = "Entrega") =>
        new(nome, "89230-210", "Rua Padre Roma, 126", "Joao Costa", "Joinville", tipo, "");

    private CriarCliente Criar() =>
        new(_clientes, _historico, _unidade, _relogio, NullLogger<CriarCliente>.Instance);

    private AtualizarCliente Atualizar() =>
        new(_clientes, _historico, _unidade, _relogio, NullLogger<AtualizarCliente>.Instance);

    private ExcluirCliente Excluir() =>
        new(_clientes, _historico, _unidade, _relogio, NullLogger<ExcluirCliente>.Instance);

    // ---------------------------------------------------------------- criar

    [Fact]
    public async Task CriarCliente_ComDadosValidos_GravaEDevolveODto()
    {
        var resultado = await Criar().ExecutarAsync(DadosValidos());

        Assert.True(resultado.Sucesso);
        Assert.Equal("Ana Paula", resultado.Valor!.Nome);
        Assert.Single(_clientes.Adicionados);
    }

    [Fact]
    public async Task CriarCliente_GravaCadastroEHistoricoNaMesmaTransacao()
    {
        await Criar().ExecutarAsync(DadosValidos());

        // Uma confirmacao so: se fossem duas, uma falha entre elas deixaria o
        // cadastro sem a linha de auditoria correspondente.
        Assert.Equal(1, _unidade.Confirmacoes);
        Assert.Single(_historico.Registrados);
        Assert.Equal(AcaoHistorico.Criacao, _historico.Registrados[0].Acao);
    }

    [Fact]
    public async Task CriarCliente_ComDadosInvalidos_NaoGravaNada()
    {
        var resultado = await Criar().ExecutarAsync(DadosValidos(nome: ""));

        Assert.False(resultado.Sucesso);
        Assert.Equal(TipoDeFalha.Validacao, resultado.Falha);
        Assert.Empty(_clientes.Adicionados);
        Assert.Empty(_historico.Registrados);
        Assert.Equal(0, _unidade.Confirmacoes);
    }

    // ------------------------------------------------------------ atualizar

    [Fact]
    public async Task AtualizarCliente_RegistraNoHistoricoOQueMudou()
    {
        var existente = _clientes.Semear(Cliente.Criar(
            "Ana Paula", "89230-210", "Rua Padre Roma, 126", "Joao Costa",
            "Joinville", "Entrega", "", Agora));

        var resultado = await Atualizar().ExecutarAsync(
            existente.Id, DadosValidos(nome: "Ana Paula Souza"));

        Assert.True(resultado.Sucesso);
        Assert.Contains("Nome", _historico.Registrados[0].Detalhes, StringComparison.Ordinal);
        Assert.Equal(AcaoHistorico.Atualizacao, _historico.Registrados[0].Acao);
    }

    [Fact]
    public async Task AtualizarCliente_Inexistente_DevolveNaoEncontrado()
    {
        var resultado = await Atualizar().ExecutarAsync(999, DadosValidos());

        // Distinguir de "dado invalido" importa: significa que a lista da tela
        // esta velha, e a resposta certa e recarregar.
        Assert.Equal(TipoDeFalha.NaoEncontrado, resultado.Falha);
        Assert.Empty(_historico.Registrados);
        Assert.Equal(0, _unidade.Confirmacoes);
    }

    [Fact]
    public async Task AtualizarCliente_ComDadosInvalidos_NaoConfirma()
    {
        var existente = _clientes.Semear(Cliente.Criar(
            "Ana Paula", "89230-210", "Rua A", "Centro", "Joinville", "Entrega", "", Agora));

        var invalidos = DadosValidos() with { Cep = "nao-e-cep" };
        var resultado = await Atualizar().ExecutarAsync(existente.Id, invalidos);

        Assert.Equal(TipoDeFalha.Validacao, resultado.Falha);
        Assert.Equal(0, _unidade.Confirmacoes);
    }

    // -------------------------------------------------------------- excluir

    [Fact]
    public async Task ExcluirCliente_RemoveERegistraNomeEEnderecoNoHistorico()
    {
        var existente = _clientes.Semear(Cliente.Criar(
            "Ana Paula", "89230-210", "Rua A", "Gloria", "Joinville", "Entrega", "", Agora));

        var resultado = await Excluir().ExecutarAsync(existente.Id);

        Assert.True(resultado.Sucesso);
        Assert.Single(_clientes.Removidos);

        // O registro precisa preservar o que sera apagado; montado depois da
        // remocao, viria vazio.
        var registro = _historico.Registrados[0];
        Assert.Equal(AcaoHistorico.Exclusao, registro.Acao);
        Assert.Contains("Ana Paula", registro.Detalhes, StringComparison.Ordinal);
        Assert.Contains("Gloria", registro.Detalhes, StringComparison.Ordinal);
        // Sem vinculo: a linha do cliente some na mesma transacao.
        Assert.Null(registro.ClienteId);
    }

    [Fact]
    public async Task ExcluirCliente_Inexistente_NaoRemoveNada()
    {
        var resultado = await Excluir().ExecutarAsync(999);

        Assert.Equal(TipoDeFalha.NaoEncontrado, resultado.Falha);
        Assert.Empty(_clientes.Removidos);
        Assert.Equal(0, _unidade.Confirmacoes);
    }

    // --------------------------------------------------------------- buscar

    [Fact]
    public async Task BuscarClientes_SemTermo_DevolveTodos()
    {
        SemearDois();

        var encontrados = await new BuscarClientes(_clientes).ExecutarAsync(null);

        Assert.Equal(2, encontrados.Count);
    }

    [Fact]
    public async Task BuscarClientes_FiltraPorNomeCidadeOuBairro()
    {
        SemearDois();

        Assert.Single(await new BuscarClientes(_clientes).ExecutarAsync("Bruno"));
        Assert.Single(await new BuscarClientes(_clientes).ExecutarAsync("Gloria"));
        Assert.Equal(2, (await new BuscarClientes(_clientes).ExecutarAsync("Joinville")).Count);
        Assert.Empty(await new BuscarClientes(_clientes).ExecutarAsync("Curitiba"));
    }

    // ------------------------------------------------------------ dashboard

    [Fact]
    public async Task Metricas_ContamPorTipoEPorJanelaDeTrintaDias()
    {
        _clientes.Semear(Cliente.Criar("Ana", "89230-210", "Rua A", "Gloria", "Joinville",
            "Entrega", "", Agora.AddDays(-2)));
        _clientes.Semear(Cliente.Criar("Bruno", "89230-210", "Rua B", "Centro", "Joinville",
            "Retirada", "", Agora.AddDays(-90)));

        var metricas = await new ObterMetricasDashboard(_clientes, _relogio).ExecutarAsync();

        Assert.Equal(2, metricas.TotalClientes);
        Assert.Equal(1, metricas.TotalEntrega);
        Assert.Equal(1, metricas.TotalRetirada);
        // O de 90 dias atras esta fora da janela.
        Assert.Equal(1, metricas.CadastrosRecentes);
    }

    [Fact]
    public async Task Metricas_UsamORelogioInjetado()
    {
        _clientes.Semear(Cliente.Criar("Ana", "89230-210", "Rua A", "Gloria", "Joinville",
            "Entrega", "", Agora));

        // Avancar o relogio um ano tira o cadastro da janela sem tocar no dado.
        _relogio.Agora = Agora.AddYears(1);
        var metricas = await new ObterMetricasDashboard(_clientes, _relogio).ExecutarAsync();

        Assert.Equal(1, metricas.TotalClientes);
        Assert.Equal(0, metricas.CadastrosRecentes);
    }

    private void SemearDois()
    {
        _clientes.Semear(Cliente.Criar("Ana Paula", "89230-210", "Rua A", "Gloria", "Joinville",
            "Entrega", "", Agora));
        _clientes.Semear(Cliente.Criar("Bruno Lima", "89230-210", "Rua B", "Centro", "Joinville",
            "Retirada", "", Agora));
    }
}
