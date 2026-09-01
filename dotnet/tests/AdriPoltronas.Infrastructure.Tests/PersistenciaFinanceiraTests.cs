using AdriPoltronas.Application.Dtos;
using AdriPoltronas.Domain.Entities;
using AdriPoltronas.Infrastructure.Persistence.Repositories;
using Microsoft.Data.Sqlite;
using Xunit;

namespace AdriPoltronas.Infrastructure.Tests;

/// <summary>
/// Mapeamento das tabelas financeiras sobre o schema que o backend Python usa.
/// </summary>
public sealed class PersistenciaFinanceiraTests : IDisposable
{
    private static readonly DateTime Agora = new(2026, 8, 28, 10, 0, 0);

    private readonly BancoLegado _banco = new();

    [Fact]
    public async Task PagamentoGravaNasColunasQueOPythonLe()
    {
        await using (var contexto = _banco.AbrirContexto())
        {
            contexto.Pagamentos.Add(Pagamento.Criar(
                7, "Doraci Pereira", 249.90m, "Poltrona", "2026-09-10", "Pix",
                "Recebido", "2026-08-20", Agora));
            await contexto.SaveChangesAsync();
        }

        using var conexao = new SqliteConnection(_banco.Conexao);
        conexao.Open();
        using var comando = conexao.CreateCommand();
        comando.CommandText =
            "SELECT cliente_id, cliente_nome, valor, status, tipo_pagamento, " +
            "data_vencimento, data_pagamento, criado_em FROM pagamentos";
        using var leitor = comando.ExecuteReader();

        Assert.True(leitor.Read());
        Assert.Equal(7, leitor.GetInt32(0));
        Assert.Equal("Doraci Pereira", leitor.GetString(1));
        Assert.Equal(249.90, leitor.GetDouble(2), 2);
        Assert.Equal("Recebido", leitor.GetString(3));
        Assert.Equal("Pix", leitor.GetString(4));
        Assert.Equal("2026-09-10", leitor.GetString(5));
        Assert.Equal("2026-08-20", leitor.GetString(6));
        // Formato de data do Python, e nao o ISO-8601 padrao do EF.
        Assert.Equal("2026-08-28 10:00:00", leitor.GetString(7));
    }

    [Fact]
    public async Task ValorEmCentavosSobreviveAoIdaEVolta()
    {
        await using (var contexto = _banco.AbrirContexto())
        {
            contexto.Pagamentos.Add(Pagamento.Criar(
                1, "Cliente", 1234.56m, "", "2026-09-10", "Pix", null, null, Agora));
            await contexto.SaveChangesAsync();
        }

        await using var leitura = _banco.AbrirContexto();
        var pagamento = leitura.Pagamentos.Single();

        Assert.Equal(1234.56m, pagamento.Valor.Valor);
    }

    [Fact]
    public async Task ArtefatosDaCobrancaVaoParaAsColunasExistentes()
    {
        await using (var contexto = _banco.AbrirContexto())
        {
            var pagamento = Pagamento.Criar(
                1, "Cliente", 100m, "", "2026-09-10", "Pix", null, null, Agora);
            pagamento.RegistrarCobrancaEmitida(
                new DadosDaCobranca("pay_1", "000201PIX", "img", "", "123"));
            contexto.Pagamentos.Add(pagamento);
            await contexto.SaveChangesAsync();
        }

        await using var leitura = _banco.AbrirContexto();
        var gravado = leitura.Pagamentos.Single();

        Assert.True(gravado.Cobranca.Emitida);
        Assert.Equal("000201PIX", gravado.Cobranca.PixPayload);
    }

    [Fact]
    public async Task EntregaGravaDataEHoraComoTexto()
    {
        await using (var contexto = _banco.AbrirContexto())
        {
            contexto.Entregas.Add(EntregaAgendada.Criar(
                3, "Ana", "2026-09-05", "14:30", "Montagem", Agora));
            await contexto.SaveChangesAsync();
        }

        using var conexao = new SqliteConnection(_banco.Conexao);
        conexao.Open();
        using var comando = conexao.CreateCommand();
        comando.CommandText =
            "SELECT data_entrega, hora_entrega, status FROM entregas_agendadas";
        using var leitor = comando.ExecuteReader();

        Assert.True(leitor.Read());
        Assert.Equal("2026-09-05", leitor.GetString(0));
        Assert.Equal("14:30", leitor.GetString(1));
        Assert.Equal("Pendente", leitor.GetString(2));
    }

    [Fact]
    public async Task MarcarAMesmaNotificacaoDuasVezesNaoQuebra()
    {
        await using var contexto = _banco.AbrirContexto();
        var repositorio = new NotificacaoLidaRepository(contexto, new RelogioParado());

        await repositorio.MarcarComoLidasAsync(["entrega_hoje:1"]);
        await repositorio.MarcarComoLidasAsync(["entrega_hoje:1", "entrega_hoje:2"]);

        var chaves = await repositorio.ChavesLidasAsync();
        Assert.Equal(2, chaves.Count);
    }

    public void Dispose() => _banco.Dispose();

    private sealed class RelogioParado : Application.Abstractions.IRelogio
    {
        public DateTime Agora => new(2026, 8, 28, 10, 0, 0);
    }
}
