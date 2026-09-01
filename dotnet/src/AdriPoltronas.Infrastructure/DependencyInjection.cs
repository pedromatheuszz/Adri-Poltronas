
using AdriPoltronas.Application.Abstractions;
using AdriPoltronas.Infrastructure.Arquivos;
using AdriPoltronas.Infrastructure.Configuration;
using AdriPoltronas.Infrastructure.Integracoes;
using AdriPoltronas.Infrastructure.Persistence;
using AdriPoltronas.Infrastructure.Persistence.Repositories;
using AdriPoltronas.Infrastructure.Sistema;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;

namespace AdriPoltronas.Infrastructure;

/// <summary>
/// Registro das implementacoes tecnicas.
/// </summary>
/// <remarks>
/// E o unico lugar que amarra interface a implementacao concreta. Trocar
/// SQLite por PostgreSQL, ou o repositorio por um dublê em teste, se resolve
/// aqui, sem tocar em caso de uso nem em ViewModel.
/// </remarks>
public static class DependencyInjection
{
    public static IServiceCollection AddInfrastructure(
        this IServiceCollection servicos, IConfiguration configuracao)
    {
        servicos.Configure<OpcoesDoBanco>(configuracao.GetSection(OpcoesDoBanco.Secao));
        servicos.Configure<OpcoesDeIntegracoes>(
            configuracao.GetSection(OpcoesDeIntegracoes.Secao));

        var integracoes = configuracao.GetSection(OpcoesDeIntegracoes.Secao)
                              .Get<OpcoesDeIntegracoes>() ?? new OpcoesDeIntegracoes();

        var opcoes = configuracao.GetSection(OpcoesDoBanco.Secao).Get<OpcoesDoBanco>()
                     ?? new OpcoesDoBanco();

        servicos.AddDbContext<AdriPoltronasDbContext>(construtor =>
        {
            switch (opcoes.Provedor)
            {
                case ProvedorDeBanco.PostgreSql:
                    // O provedor do PostgreSQL (Npgsql) ainda nao e referenciado:
                    // acrescentar o pacote hoje seria uma dependencia sem uso. A
                    // fronteira ja esta pronta -- o que muda e esta linha, e nada
                    // mais no restante da aplicacao.
                    throw new NotSupportedException(
                        "Provedor PostgreSQL ainda nao habilitado. Adicione o pacote " +
                        "Npgsql.EntityFrameworkCore.PostgreSQL e troque esta linha por " +
                        "UseNpgsql(conexao).");

                default:
                    construtor.UseSqlite(ConexaoSqlite(opcoes));
                    break;
            }
        });

        servicos.AddScoped<IClienteRepository, ClienteRepository>();
        servicos.AddScoped<IHistoricoRepository, HistoricoRepository>();
        servicos.AddScoped<IPagamentoRepository, PagamentoRepository>();
        servicos.AddScoped<IEntregaRepository, EntregaRepository>();
        servicos.AddScoped<INotificacaoLidaRepository, NotificacaoLidaRepository>();
        servicos.AddScoped<IDashboardRepository, DashboardRepository>();
        servicos.AddScoped<IUnidadeDeTrabalho, UnidadeDeTrabalho>();
        servicos.AddScoped<InicializadorDoBanco>();

        servicos.AddScoped<IExportadorDePlanilha, ExportadorDePlanilha>();
        servicos.AddScoped<IImportadorDePlanilha, ImportadorDePlanilha>();
        servicos.AddScoped<IServicoDeBackup, ServicoDeBackup>();

        RegistrarIntegracoes(servicos, integracoes);

        // O relogio nao tem estado: uma instancia serve a aplicacao inteira.
        servicos.AddSingleton<IRelogio, RelogioDoSistema>();

        return servicos;
    }

    /// <summary>
    /// Clientes HTTP dos servicos externos.
    /// </summary>
    /// <remarks>
    /// Um <see cref="HttpClient"/> tipado por integracao, e nao um compartilhado:
    /// cada servico tem seu proprio cabecalho de identificacao e seu proprio
    /// tempo limite. A fabrica cuida do descarte de conexao, que e a armadilha
    /// classica de instanciar HttpClient a cada chamada.
    ///
    /// O geocodificador e singleton porque guarda o cache de coordenadas e
    /// serializa as chamadas para respeitar o limite do servico -- uma
    /// instancia por escopo perderia as duas coisas.
    /// </remarks>
    private static void RegistrarIntegracoes(
        IServiceCollection servicos, OpcoesDeIntegracoes opcoes)
    {
        var tempoLimite = TimeSpan.FromSeconds(Math.Clamp(opcoes.TempoLimiteEmSegundos, 3, 60));

        servicos.AddHttpClient<IConsultaDeCep, ConsultaDeCepViaCep>(cliente =>
        {
            cliente.Timeout = tempoLimite;
            cliente.DefaultRequestHeaders.UserAgent.ParseAdd(
                opcoes.IdentificacaoDoGeocodificador);
        });

        servicos.AddHttpClient<ISugestaoDeBairro, SugestaoDeBairroGemini>(cliente =>
            cliente.Timeout = tempoLimite);

        servicos.AddHttpClient<IServicoDeCobranca, ServicoDeCobrancaAsaas>(cliente =>
        {
            cliente.Timeout = tempoLimite;
            cliente.DefaultRequestHeaders.UserAgent.ParseAdd("AdriPoltronas/1.0");

            // A chave e cabecalho fixo do cliente: nao passa por parametro de
            // metodo nem aparece em log de chamada.
            if (!string.IsNullOrWhiteSpace(opcoes.ChaveDoAsaas))
            {
                cliente.DefaultRequestHeaders.Add("access_token", opcoes.ChaveDoAsaas);
            }
        });

        servicos.AddHttpClient<GeocodificadorNominatim>(cliente =>
        {
            cliente.Timeout = tempoLimite;
            // O Nominatim recusa requisicao sem identificacao da aplicacao.
            cliente.DefaultRequestHeaders.UserAgent.ParseAdd(
                opcoes.IdentificacaoDoGeocodificador);
        });
        servicos.AddSingleton<IGeocodificador>(provedor =>
            provedor.GetRequiredService<GeocodificadorNominatim>());
    }

    private static string ConexaoSqlite(OpcoesDoBanco opcoes) =>
        string.IsNullOrWhiteSpace(opcoes.ConexaoString)
            ? $"Data Source={PastaDeDados.CaminhoDoBanco()}"
            : opcoes.ConexaoString;
}
