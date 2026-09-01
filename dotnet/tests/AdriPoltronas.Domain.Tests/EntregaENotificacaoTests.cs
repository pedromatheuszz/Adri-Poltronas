using AdriPoltronas.Domain.Entities;
using AdriPoltronas.Domain.Enums;
using AdriPoltronas.Domain.Exceptions;
using Xunit;

namespace AdriPoltronas.Domain.Tests;

public sealed class EntregaAgendadaTests
{
    private static readonly DateTime Agora = new(2026, 8, 28, 10, 0, 0);

    [Fact]
    public void HoraForaDoFormatoERecusada()
    {
        Assert.Throws<ValidacaoException>(() =>
            EntregaAgendada.Criar(1, "Cliente", "2026-08-30", "25:00", "", Agora));
    }

    [Fact]
    public void HoraVaziaEAceita()
    {
        // Ha entregas combinadas so pelo dia.
        var entrega = EntregaAgendada.Criar(1, "Cliente", "2026-08-30", null, "", Agora);

        Assert.Equal(string.Empty, entrega.HoraEntrega);
    }

    [Fact]
    public void ClienteInvalidoERecusado()
    {
        Assert.Throws<ValidacaoException>(() =>
            EntregaAgendada.Criar(0, "Cliente", "2026-08-30", "10:00", "", Agora));
    }

    [Fact]
    public void DiasAteENegativoQuandoJaPassou()
    {
        var entrega = EntregaAgendada.Criar(1, "Cliente", "2026-08-20", null, "", Agora);

        Assert.Equal(-8, entrega.DiasAte(Agora));
    }

    [Fact]
    public void CanceladaNaoPodeSerConcluida()
    {
        var entrega = EntregaAgendada.Criar(1, "Cliente", "2026-08-30", null, "", Agora);
        entrega.Cancelar();

        Assert.Throws<DomainException>(entrega.Concluir);
    }
}

public sealed class RegrasDeNotificacaoTests
{
    private static readonly DateTime Agora = new(2026, 8, 28, 10, 0, 0);

    [Theory]
    [InlineData("2026-08-20", TipoNotificacao.EntregaAtrasada)]
    [InlineData("2026-08-28", TipoNotificacao.EntregaHoje)]
    [InlineData("2026-08-30", TipoNotificacao.EntregaProxima)]
    public void OTipoDoAlertaVemDaDistanciaAteAEntrega(string data, TipoNotificacao esperado)
    {
        var entrega = EntregaAgendada.Criar(1, "Cliente", data, null, "", Agora);

        var alerta = RegrasDeNotificacao.DeEntrega(entrega, Agora);

        Assert.Equal(esperado, alerta.Tipo);
    }

    [Fact]
    public void AChaveEEstavelEntreExecucoes()
    {
        // Chave instavel faz o alerta dispensado reaparecer na proxima abertura.
        var entrega = EntregaAgendada.Criar(1, "Cliente", "2026-08-30", null, "", Agora);
        DefinirId(entrega, 42);

        var primeira = RegrasDeNotificacao.DeEntrega(entrega, Agora).Chave;
        var segunda = RegrasDeNotificacao.DeEntrega(entrega, Agora.AddHours(3)).Chave;

        Assert.Equal(primeira, segunda);
        Assert.Contains("42", primeira, StringComparison.Ordinal);
    }

    [Fact]
    public void EntregaAtrasadaTemPrioridadeMaiorQueClienteInativo()
    {
        var entrega = EntregaAgendada.Criar(1, "Cliente", "2026-08-01", null, "", Agora);
        var cliente = Cliente.Criar(
            "Antigo", "89230-210", "Rua", "Centro", "Joinville", "Entrega", "",
            Agora.AddDays(-200));

        var doAtraso = RegrasDeNotificacao.DeEntrega(entrega, Agora);
        var doInativo = RegrasDeNotificacao.DeClienteInativo(cliente, Agora);

        Assert.True(doAtraso.Prioridade > doInativo.Prioridade);
    }

    [Fact]
    public void PagamentoVencidoViraAlertaDeAtraso()
    {
        var pagamento = Pagamento.Criar(
            1, "Cliente", 100m, "", "2026-08-01", "Pix", "Pendente", null, Agora);

        var alerta = RegrasDeNotificacao.DePagamento(pagamento, Agora);

        Assert.Equal(TipoNotificacao.PagamentoAtrasado, alerta.Tipo);
    }

    private static void DefinirId(EntregaAgendada entrega, int id) =>
        typeof(EntregaAgendada).GetProperty(nameof(EntregaAgendada.Id))!
            .SetValue(entrega, id);
}
