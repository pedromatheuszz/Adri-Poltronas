using AdriPoltronas.Domain.Entities;
using AdriPoltronas.Domain.Enums;
using AdriPoltronas.Infrastructure.Configuration;
using AdriPoltronas.Infrastructure.Persistence;
using AdriPoltronas.Infrastructure.Persistence.Configurations;
using AdriPoltronas.Infrastructure.Persistence.Repositories;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.Extensions.Options;
using Xunit;

namespace AdriPoltronas.Infrastructure.Tests;

/// <summary>
/// O mapeamento do EF Core contra a base que ja existe.
/// </summary>
/// <remarks>
/// Aqui nao ha dublê: o teste abre um arquivo SQLite de verdade com o schema
/// de producao. E o que responde a pergunta que decide a migracao -- o
/// aplicativo .NET consegue ler e gravar a mesma base do backend Python, sem
/// conversao e sem perder dado?
/// </remarks>
public sealed class PersistenciaTests
{
    private static readonly DateTime Agora = new(2026, 8, 28, 14, 30, 0);

    [Fact]
    public async Task LeCadastroGravadoPeloBackendPython()
    {
        using var banco = new BancoLegado();
        banco.InserirComoOPythonInsere(
            "Doraci Pereira da Silva", "89230-210", "Rua Padre Roma, 126",
            "Joao Costa", "Joinville", "Retirada", "2026-08-08 09:27:54");

        await using var contexto = banco.AbrirContexto();
        var repositorio = new ClienteRepository(contexto);

        var clientes = await repositorio.BuscarAsync(null);

        var cliente = Assert.Single(clientes);
        Assert.Equal("Doraci Pereira da Silva", cliente.Nome);
        Assert.Equal("89230-210", cliente.Endereco.Cep.Valor);
        Assert.Equal("Joao Costa", cliente.Endereco.Bairro);
        Assert.Equal(TipoAtendimento.Retirada, cliente.Tipo);
        Assert.Equal(new DateTime(2026, 8, 8, 9, 27, 54), cliente.CriadoEm);
    }

    [Fact]
    public async Task GravaNoMesmoFormatoDeDataQueOPythonEspera()
    {
        using var banco = new BancoLegado();
        await using (var contexto = banco.AbrirContexto())
        {
            contexto.Clientes.Add(Cliente.Criar("Ana Paula", "89230-210", "Rua A", "Centro",
                "Joinville", "Entrega", "", Agora));
            await contexto.SaveChangesAsync();
        }

        var gravado = banco.LerTexto("SELECT criado_em FROM clientes LIMIT 1");

        // O filtro de metricas do backend compara a coluna como texto contra
        // datetime('now','-30 days'). Com o "T" e a fracao de segundo do
        // ISO-8601 padrao do EF, os cadastros feitos pelo .NET sumiriam da
        // contagem do Python.
        Assert.Equal("2026-08-28 14:30:00", gravado);
        Assert.DoesNotContain("T", gravado, StringComparison.Ordinal);
    }

    [Fact]
    public async Task GravaOTipoComoTextoENaoComoNumero()
    {
        using var banco = new BancoLegado();
        await using (var contexto = banco.AbrirContexto())
        {
            contexto.Clientes.Add(Cliente.Criar("Ana", "89230-210", "Rua A", "Centro",
                "Joinville", "Retirada", "", Agora));
            await contexto.SaveChangesAsync();
        }

        // O backend Python compara entrega_retirada='Entrega' nas metricas.
        Assert.Equal("Retirada", banco.LerTexto("SELECT entrega_retirada FROM clientes LIMIT 1"));
    }

    [Fact]
    public async Task ColunasNaoUsadasPeloDominioMantemODefaultDoSchema()
    {
        // `ativo` e NOT NULL e o modelo .NET nem sabe que ela existe. Se o EF
        // tentasse inserir sem ela e sem default, o insert falharia.
        using var banco = new BancoLegado();
        await using var contexto = banco.AbrirContexto();
        contexto.Clientes.Add(Cliente.Criar("Ana", "89230-210", "Rua A", "Centro",
            "Joinville", "Entrega", "", Agora));

        await contexto.SaveChangesAsync();

        Assert.Equal("1", banco.LerTexto("SELECT ativo FROM clientes LIMIT 1"));
    }

    [Fact]
    public async Task CadastroEHistoricoEntramNaMesmaGravacao()
    {
        using var banco = new BancoLegado();
        await using var contexto = banco.AbrirContexto();
        var cliente = Cliente.Criar("Ana", "89230-210", "Rua A", "Centro", "Joinville",
            "Entrega", "", Agora);

        contexto.Clientes.Add(cliente);
        // O registro aponta para a entidade, nao para um id: no momento em que
        // e criado, o id do cliente ainda e 0.
        contexto.Historico.Add(RegistroHistorico.Criacao(cliente, Agora));
        await contexto.SaveChangesAsync();

        Assert.Equal(1, banco.Contar("clientes"));
        Assert.Equal(1, banco.Contar("historico"));
        // O ORM preencheu a chave estrangeira depois do insert do cliente.
        Assert.Equal(cliente.Id.ToString(), banco.LerTexto("SELECT cliente_id FROM historico"));
        Assert.Equal("CRIACAO", banco.LerTexto("SELECT acao FROM historico"));
    }

    [Fact]
    public async Task ExclusaoPreservaOHistoricoSemChaveEstrangeiraQuebrada()
    {
        using var banco = new BancoLegado();
        await using var contexto = banco.AbrirContexto();
        var cliente = Cliente.Criar("Ana", "89230-210", "Rua A", "Gloria", "Joinville",
            "Entrega", "", Agora);
        contexto.Clientes.Add(cliente);
        await contexto.SaveChangesAsync();

        var registro = RegistroHistorico.Exclusao(cliente, Agora);
        contexto.Clientes.Remove(cliente);
        contexto.Historico.Add(registro);
        await contexto.SaveChangesAsync();

        Assert.Equal(0, banco.Contar("clientes"));
        Assert.Equal(1, banco.Contar("historico"));
        Assert.Contains("Gloria", banco.LerTexto("SELECT detalhes FROM historico"),
            StringComparison.Ordinal);
    }

    [Fact]
    public async Task BuscaFiltraPorNomeCidadeOuBairro()
    {
        using var banco = new BancoLegado();
        banco.InserirComoOPythonInsere("Ana Paula", "89230-210", "Rua A", "Gloria",
            "Joinville", "Entrega", "2026-08-01 10:00:00");
        banco.InserirComoOPythonInsere("Bruno Lima", "89230-210", "Rua B", "Centro",
            "Curitiba", "Retirada", "2026-08-02 10:00:00");

        await using var contexto = banco.AbrirContexto();
        var repositorio = new ClienteRepository(contexto);

        Assert.Single(await repositorio.BuscarAsync("Bruno"));
        Assert.Single(await repositorio.BuscarAsync("Gloria"));
        Assert.Single(await repositorio.BuscarAsync("Curitiba"));
        Assert.Empty(await repositorio.BuscarAsync("Florianopolis"));
    }

    [Fact]
    public async Task BuscaDevolveOsMaisRecentesPrimeiro()
    {
        using var banco = new BancoLegado();
        banco.InserirComoOPythonInsere("Primeiro", "89230-210", "Rua A", "Centro",
            "Joinville", "Entrega", "2026-08-01 10:00:00");
        banco.InserirComoOPythonInsere("Segundo", "89230-210", "Rua B", "Centro",
            "Joinville", "Entrega", "2026-08-02 10:00:00");

        await using var contexto = banco.AbrirContexto();
        var clientes = await new ClienteRepository(contexto).BuscarAsync(null);

        Assert.Equal("Segundo", clientes[0].Nome);
    }

    [Fact]
    public async Task MetricasContamPorTipoEPelaJanelaDeDatas()
    {
        using var banco = new BancoLegado();
        banco.InserirComoOPythonInsere("Ana", "89230-210", "Rua A", "Centro", "Joinville",
            "Entrega", "2026-08-20 10:00:00");
        banco.InserirComoOPythonInsere("Bruno", "89230-210", "Rua B", "Centro", "Joinville",
            "Retirada", "2026-08-25 10:00:00");
        banco.InserirComoOPythonInsere("Antigo", "89230-210", "Rua C", "Centro", "Joinville",
            "Entrega", "2025-01-05 10:00:00");

        await using var contexto = banco.AbrirContexto();
        var metricas = await new ClienteRepository(contexto)
            .ObterMetricasAsync(new DateTime(2026, 7, 29, 14, 30, 0));

        Assert.Equal(3, metricas.TotalClientes);
        Assert.Equal(2, metricas.TotalEntrega);
        Assert.Equal(1, metricas.TotalRetirada);
        // A comparacao de data acontece no banco, sobre texto: so funciona
        // porque o formato gravado ordena igual a ordem cronologica.
        Assert.Equal(2, metricas.CadastrosRecentes);
    }

    [Fact]
    public async Task MetricasEmBaseVaziaNaoQuebram()
    {
        using var banco = new BancoLegado();
        await using var contexto = banco.AbrirContexto();

        var metricas = await new ClienteRepository(contexto).ObterMetricasAsync(Agora.AddDays(-30));

        Assert.Equal(0, metricas.TotalClientes);
    }

    [Fact]
    public async Task CadastroAntigoComCepVazioNaoDerrubaAListagem()
    {
        // Ha registros anteriores a validacao de CEP na base real. Se a leitura
        // validasse, a lista inteira falharia por causa deles.
        using var banco = new BancoLegado();
        banco.InserirComoOPythonInsere("Teste CSRF", "", "", "", "", "Entrega",
            "2026-08-12 01:28:30");

        await using var contexto = banco.AbrirContexto();
        var clientes = await new ClienteRepository(contexto).BuscarAsync(null);

        var cliente = Assert.Single(clientes);
        Assert.Equal(string.Empty, cliente.Endereco.Cep.Valor);
    }

    // --------------------------------------------------------- inicializacao

    [Fact]
    public async Task NaoAplicaMigracaoQuandoOSchemaEDoAlembic()
    {
        // O schema do banco em uso e versionado pelo Alembic. Se o EF tambem
        // migrasse, as duas ferramentas disputariam as mesmas tabelas.
        using var banco = new BancoLegado(comAlembic: true);
        await using var contexto = banco.AbrirContexto();
        var inicializador = new InicializadorDoBanco(
            contexto,
            Options.Create(new OpcoesDoBanco { AplicarMigracoes = true }),
            NullLogger<InicializadorDoBanco>.Instance);

        await inicializador.PrepararAsync();

        // As tabelas continuam as originais, e nada foi recriado.
        Assert.Equal(1, banco.Contar("alembic_version"));
        Assert.Equal(0, banco.Contar("clientes"));
    }

    [Fact]
    public void FormatoDeDataEOMesmoDoSchemaLegado()
    {
        Assert.Equal("yyyy-MM-dd HH:mm:ss", ConversoresDeData.Formato);
    }
}
