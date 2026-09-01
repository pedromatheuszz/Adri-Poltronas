using AdriPoltronas.Application.Dtos;
using AdriPoltronas.Application.UseCases.Pagamentos;
using AdriPoltronas.Domain.Entities;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace AdriPoltronas.Application.Tests;

public sealed class CasosDeUsoDePagamentoTests
{
    private static readonly DateTime Agora = new(2026, 8, 28, 10, 0, 0);

    private readonly RepositorioFalsoDePagamentos _pagamentos = new();
    private readonly RepositorioFalsoDeClientes _clientes = new();
    private readonly UnidadeDeTrabalhoFalsa _unidade = new();
    private readonly RelogioFalso _relogio = new(Agora);
    private readonly CobrancaFalsa _cobrancas = new();

    [Fact]
    public async Task RegistrarRecusaClienteInexistente()
    {
        var caso = new RegistrarPagamento(
            _pagamentos, _clientes, _unidade, _relogio,
            NullLogger<RegistrarPagamento>.Instance);

        var resultado = await caso.ExecutarAsync(
            new DadosDoPagamento(999, "Fantasma", 100m, "", "2026-09-01", "Pix", null, null));

        Assert.False(resultado.Sucesso);
        Assert.Empty(_pagamentos.Adicionados);
    }

    [Fact]
    public async Task RegistrarUsaONomeDoCadastroENaoODigitado()
    {
        // O nome e copiado para a linha; deixar o formulario mandar o dele
        // permitiria uma cobranca com nome que nao existe no cadastro.
        var cliente = SemearCliente();

        var caso = new RegistrarPagamento(
            _pagamentos, _clientes, _unidade, _relogio,
            NullLogger<RegistrarPagamento>.Instance);

        var resultado = await caso.ExecutarAsync(
            new DadosDoPagamento(cliente.Id, "Outro nome", 100m, "", "2026-09-01", "Pix",
                null, null));

        Assert.True(resultado.Sucesso);
        Assert.Equal(cliente.Nome, resultado.Valor!.ClienteNome);
    }

    [Fact]
    public async Task RegistrarValorInvalidoNaoGrava()
    {
        var cliente = SemearCliente();
        var caso = new RegistrarPagamento(
            _pagamentos, _clientes, _unidade, _relogio,
            NullLogger<RegistrarPagamento>.Instance);

        var resultado = await caso.ExecutarAsync(
            new DadosDoPagamento(cliente.Id, null, 0m, "", "2026-09-01", "Pix", null, null));

        Assert.False(resultado.Sucesso);
        Assert.Equal(0, _unidade.Confirmacoes);
    }

    [Fact]
    public async Task ConfirmarMarcaComoRecebido()
    {
        var pagamento = SemearPagamento();
        var caso = new ConfirmarPagamento(
            _pagamentos, _unidade, _relogio, NullLogger<ConfirmarPagamento>.Instance);

        var resultado = await caso.ExecutarAsync(pagamento.Id);

        Assert.True(resultado.Sucesso);
        Assert.Equal("Recebido", resultado.Valor!.Status);
        Assert.Equal(1, _unidade.Confirmacoes);
    }

    [Fact]
    public async Task CancelarRecebidoVoltaComoInvalidoENaoComoExcecao()
    {
        var pagamento = SemearPagamento(status: "Recebido");
        var caso = new CancelarPagamento(
            _pagamentos, _unidade, _relogio, NullLogger<CancelarPagamento>.Instance);

        var resultado = await caso.ExecutarAsync(pagamento.Id);

        Assert.False(resultado.Sucesso);
        Assert.Equal(0, _unidade.Confirmacoes);
    }

    [Fact]
    public async Task ExcluirInexistenteInformaEmVezDeEstourar()
    {
        var caso = new ExcluirPagamento(
            _pagamentos, _unidade, NullLogger<ExcluirPagamento>.Instance);

        var resultado = await caso.ExecutarAsync(999);

        Assert.False(resultado.Sucesso);
    }

    [Fact]
    public async Task GerarCobrancaGuardaOCodigoPix()
    {
        var pagamento = SemearPagamento();
        var caso = new GerarCobranca(
            _pagamentos, _cobrancas, _unidade, _relogio, NullLogger<GerarCobranca>.Instance);

        var resultado = await caso.ExecutarAsync(pagamento.Id);

        Assert.True(resultado.Sucesso);
        Assert.Equal("000201PIX", resultado.Valor!.PixPayload);
        Assert.Equal(1, _unidade.Confirmacoes);
    }

    [Fact]
    public async Task GerarCobrancaDuasVezesNaoEmiteOutra()
    {
        // Emitir de novo daria ao cliente dois codigos Pix para a mesma divida.
        var pagamento = SemearPagamento();
        var caso = new GerarCobranca(
            _pagamentos, _cobrancas, _unidade, _relogio, NullLogger<GerarCobranca>.Instance);

        await caso.ExecutarAsync(pagamento.Id);
        await caso.ExecutarAsync(pagamento.Id);

        Assert.Equal(1, _cobrancas.Emissoes);
    }

    [Fact]
    public async Task GerarCobrancaEmDinheiroERecusada()
    {
        var pagamento = SemearPagamento(tipo: "Dinheiro");
        var caso = new GerarCobranca(
            _pagamentos, _cobrancas, _unidade, _relogio, NullLogger<GerarCobranca>.Instance);

        var resultado = await caso.ExecutarAsync(pagamento.Id);

        Assert.False(resultado.Sucesso);
        Assert.Equal(0, _cobrancas.Emissoes);
    }

    [Fact]
    public async Task SemChaveDeApiACobrancaOnlineNaoEChamada()
    {
        _cobrancas.Configurado = false;
        var pagamento = SemearPagamento();
        var caso = new GerarCobranca(
            _pagamentos, _cobrancas, _unidade, _relogio, NullLogger<GerarCobranca>.Instance);

        var resultado = await caso.ExecutarAsync(pagamento.Id);

        Assert.False(resultado.Sucesso);
        Assert.Equal(0, _cobrancas.Emissoes);
    }

    [Fact]
    public async Task BuscarFiltraPorStatus()
    {
        SemearPagamento();
        SemearPagamento(status: "Recebido");

        var caso = new BuscarPagamentos(_pagamentos, _relogio);
        var encontrados = await caso.ExecutarAsync(new FiltroDePagamentos(null, "Recebido"));

        Assert.Single(encontrados);
        Assert.Equal("Recebido", encontrados[0].Status);
    }

    private Cliente SemearCliente() => _clientes.Semear(Cliente.Criar(
        "Doraci Pereira", "89230-210", "Rua Padre Roma", "Centro", "Joinville",
        "Entrega", "", Agora));

    private Pagamento SemearPagamento(string? status = "Pendente", string? tipo = "Pix") =>
        _pagamentos.Semear(Pagamento.Criar(
            1, "Doraci Pereira", 200m, "Poltrona", "2026-09-10", tipo, status, null, Agora));
}
