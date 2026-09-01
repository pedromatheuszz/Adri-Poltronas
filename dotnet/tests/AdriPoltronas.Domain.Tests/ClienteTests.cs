using AdriPoltronas.Domain.Entities;
using AdriPoltronas.Domain.Enums;
using AdriPoltronas.Domain.Exceptions;
using Xunit;

namespace AdriPoltronas.Domain.Tests;

/// <summary>
/// Regras do cadastro de cliente.
/// </summary>
/// <remarks>
/// Estas regras viviam em <c>backend/validators.py</c> e eram exercitadas
/// pelos testes Python. Ao trazer a regra para o Domain, o teste vem junto --
/// caso contrario a migracao moveria codigo e deixaria a rede de seguranca
/// para tras.
/// </remarks>
public sealed class ClienteTests
{
    private static readonly DateTime Agora = new(2026, 8, 28, 14, 30, 0);

    private static Cliente CriarValido() => Cliente.Criar(
        nome: "Doraci Pereira da Silva",
        cep: "89230-210",
        rua: "Rua Padre Roma, 126",
        bairro: "Joao Costa",
        cidade: "Joinville",
        tipo: "Retirada",
        observacoes: "portao azul",
        agora: Agora);

    [Fact]
    public void Criar_ComDadosValidos_PreencheOCadastro()
    {
        var cliente = CriarValido();

        Assert.Equal("Doraci Pereira da Silva", cliente.Nome);
        Assert.Equal("89230-210", cliente.Endereco.Cep.Valor);
        Assert.Equal(TipoAtendimento.Retirada, cliente.Tipo);
        Assert.Equal(Agora, cliente.CriadoEm);
        Assert.Equal(Agora, cliente.AtualizadoEm);
    }

    [Theory]
    [InlineData("89230210")]
    [InlineData("89230-210")]
    [InlineData("  89230210  ")]
    public void Criar_NormalizaOCepParaOFormatoCanonico(string entrada)
    {
        var cliente = Cliente.Criar("Ana Paula", entrada, "Rua A", "Centro", "Joinville",
            "Entrega", "", Agora);

        // Sem a normalizacao, "89230210" e "89230-210" viravam dois cadastros
        // distintos na deteccao de duplicados da importacao.
        Assert.Equal("89230-210", cliente.Endereco.Cep.Valor);
    }

    [Theory]
    [InlineData("123")]
    [InlineData("abcdefgh")]
    [InlineData("")]
    [InlineData("1234567890")]
    public void Criar_ComCepInvalido_Recusa(string cep)
    {
        var erro = Assert.Throws<ValidacaoException>(() =>
            Cliente.Criar("Ana Paula", cep, "Rua A", "Centro", "Joinville", "Entrega", "", Agora));

        Assert.Contains(erro.Erros, e => e.Contains("CEP", StringComparison.Ordinal));
    }

    [Fact]
    public void Criar_SemNome_Recusa()
    {
        var erro = Assert.Throws<ValidacaoException>(() =>
            Cliente.Criar("  ", "89230-210", "Rua A", "Centro", "Joinville", "Entrega", "", Agora));

        Assert.Contains(erro.Erros, e => e.StartsWith("Nome", StringComparison.Ordinal));
    }

    [Fact]
    public void Criar_ComTipoForaDasOpcoes_Recusa()
    {
        var erro = Assert.Throws<ValidacaoException>(() =>
            Cliente.Criar("Ana", "89230-210", "Rua A", "Centro", "Joinville", "Devolucao", "", Agora));

        Assert.Contains(erro.Erros, e => e.Contains("Entrega/Retirada", StringComparison.Ordinal));
    }

    [Fact]
    public void Criar_AcumulaTodosOsErrosDeUmaVez()
    {
        // O formulario mostra tudo junto; devolver so o primeiro erro faria o
        // operador corrigir um campo por tentativa.
        var erro = Assert.Throws<ValidacaoException>(() =>
            Cliente.Criar("", "invalido", "", "", "", "", "", Agora));

        Assert.True(erro.Erros.Count >= 5, $"esperava varios erros, veio {erro.Erros.Count}");
    }

    [Fact]
    public void Criar_ColapsaEspacosEAparaAsPontas()
    {
        var cliente = Cliente.Criar("  Ana    Paula  ", "89230-210", " Rua A ", "Centro",
            "Joinville", "Entrega", "", Agora);

        Assert.Equal("Ana Paula", cliente.Nome);
        Assert.Equal("Rua A", cliente.Endereco.Rua);
    }

    [Fact]
    public void Criar_AceitaAcentoEPontuacaoDeEndereco()
    {
        var cliente = Cliente.Criar("Antonio d'Avila", "89230-210", "Rua Sao Joao, 12 - fundos",
            "Gloria", "Joinville", "Entrega", "", Agora);

        Assert.Equal("Antonio d'Avila", cliente.Nome);
    }

    [Fact]
    public void Criar_RecusaCaractereQueNaoPertenceAUmCadastro()
    {
        var erro = Assert.Throws<ValidacaoException>(() =>
            Cliente.Criar("<script>alert(1)</script>", "89230-210", "Rua A", "Centro",
                "Joinville", "Entrega", "", Agora));

        Assert.Contains(erro.Erros, e => e.Contains("invalidos", StringComparison.Ordinal));
    }

    [Fact]
    public void Atualizar_DescreveApenasOsCamposQueMudaram()
    {
        var cliente = CriarValido();
        var depois = Agora.AddHours(2);

        var mudancas = cliente.Atualizar(
            "Doraci Pereira da Silva", "89230-210", "Rua Padre Roma, 126", "Joao Costa",
            "Joinville", "Entrega", "portao azul", depois);

        Assert.Equal(["Tipo: 'Retirada' -> 'Entrega'"], mudancas);
        Assert.Equal(TipoAtendimento.Entrega, cliente.Tipo);
        Assert.Equal(depois, cliente.AtualizadoEm);
        Assert.Equal(Agora, cliente.CriadoEm);
    }

    [Fact]
    public void Atualizar_ComOsMesmosDados_NaoRegistraMudanca()
    {
        var cliente = CriarValido();

        // Espaco a mais no fim do nome nao e alteracao: a comparacao acontece
        // depois da normalizacao, e nao sobre o texto cru digitado.
        var mudancas = cliente.Atualizar(
            "Doraci Pereira da Silva  ", "89230210", "Rua Padre Roma, 126", "Joao Costa",
            "Joinville", "Retirada", "portao azul", Agora.AddMinutes(5));

        Assert.Empty(mudancas);
    }

    [Fact]
    public void Atualizar_ComDadoInvalido_NaoAlteraOCliente()
    {
        var cliente = CriarValido();

        Assert.Throws<ValidacaoException>(() =>
            cliente.Atualizar("Novo Nome", "cep-ruim", "Rua B", "Centro", "Joinville",
                "Entrega", "", Agora.AddHours(1)));

        // A entidade nao pode ficar meio atualizada quando a validacao falha.
        Assert.Equal("Doraci Pereira da Silva", cliente.Nome);
        Assert.Equal(TipoAtendimento.Retirada, cliente.Tipo);
        Assert.Equal(Agora, cliente.AtualizadoEm);
    }
}
