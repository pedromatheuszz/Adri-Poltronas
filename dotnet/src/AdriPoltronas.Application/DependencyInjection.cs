using AdriPoltronas.Application.UseCases.Clientes;
using AdriPoltronas.Application.UseCases.Dados;
using AdriPoltronas.Application.UseCases.Dashboard;
using AdriPoltronas.Application.UseCases.Enderecos;
using AdriPoltronas.Application.UseCases.Entregas;
using AdriPoltronas.Application.UseCases.Mapa;
using AdriPoltronas.Application.UseCases.Notificacoes;
using AdriPoltronas.Application.UseCases.Pagamentos;
using AdriPoltronas.Application.UseCases.Relatorios;
using Microsoft.Extensions.DependencyInjection;

namespace AdriPoltronas.Application;

/// <summary>
/// Registro dos casos de uso.
/// </summary>
/// <remarks>
/// Cada camada expoe o proprio metodo de registro e o Desktop apenas os
/// encadeia. Assim quem adiciona um caso de uso mexe aqui, e nao no arranque
/// da aplicacao -- e a Application nao precisa ser aberta pela UI para
/// descobrir o que existe.
/// </remarks>
public static class DependencyInjection
{
    public static IServiceCollection AddApplication(this IServiceCollection servicos)
    {
        // Scoped, e nao singleton: cada operacao da tela roda no seu escopo,
        // com o proprio DbContext, e o rastreamento de entidades de uma edicao
        // nao vaza para a proxima.
        servicos.AddScoped<CriarCliente>();
        servicos.AddScoped<AtualizarCliente>();
        servicos.AddScoped<ExcluirCliente>();
        servicos.AddScoped<BuscarClientes>();
        servicos.AddScoped<ObterCliente>();

        servicos.AddScoped<ObterMetricasDashboard>();
        servicos.AddScoped<ObterPainel>();

        servicos.AddScoped<BuscarPagamentos>();
        servicos.AddScoped<ObterMetricasPagamentos>();
        servicos.AddScoped<RegistrarPagamento>();
        servicos.AddScoped<ConfirmarPagamento>();
        servicos.AddScoped<CancelarPagamento>();
        servicos.AddScoped<ExcluirPagamento>();
        servicos.AddScoped<GerarCobranca>();

        servicos.AddScoped<BuscarEntregas>();
        servicos.AddScoped<AgendarEntrega>();
        servicos.AddScoped<ConcluirEntrega>();
        servicos.AddScoped<ExcluirEntrega>();

        servicos.AddScoped<ObterNotificacoes>();
        servicos.AddScoped<MarcarNotificacoesLidas>();

        servicos.AddScoped<GerarRelatorio>();
        servicos.AddScoped<ExportarRelatorio>();
        servicos.AddScoped<ObterDesempenhoPorRegiao>();

        servicos.AddScoped<ConsultarEndereco>();
        servicos.AddScoped<ObterPontosDoMapa>();

        servicos.AddScoped<ImportarClientes>();
        servicos.AddScoped<ExportarClientes>();
        servicos.AddScoped<FazerBackup>();
        return servicos;
    }
}
