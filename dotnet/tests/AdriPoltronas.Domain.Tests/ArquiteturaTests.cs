using System.Reflection;
using AdriPoltronas.Domain.Entities;
using Xunit;

namespace AdriPoltronas.Domain.Tests;

/// <summary>
/// Verifica a direcao das dependencias entre as camadas.
/// </summary>
/// <remarks>
/// Uma regra de arquitetura que so existe em documento e uma regra que sera
/// quebrada na primeira pressa: basta um <c>using</c> conveniente para o
/// Domain passar a depender do Entity Framework, e nada acusa ate alguem tentar
/// testar a regra de negocio sem banco.
///
/// O teste vive no projeto do Domain porque e a camada que precisa continuar
/// isolada. Ele inspeciona os assemblies referenciados, entao pega tambem
/// dependencia indireta.
/// </remarks>
public sealed class ArquiteturaTests
{
    private static readonly Assembly Dominio = typeof(Cliente).Assembly;

    /// <summary>Tecnologias que nao podem alcancar o Domain.</summary>
    private static readonly string[] Proibidos =
    [
        "Avalonia",
        "Microsoft.EntityFrameworkCore",
        "Microsoft.Data.Sqlite",
        "Npgsql",
        "CommunityToolkit",
        "AdriPoltronas.Application",
        "AdriPoltronas.Infrastructure",
        "AdriPoltronas.Desktop",
    ];

    [Fact]
    public void Dominio_NaoDependeDeInterfaceNemDeInfraestrutura()
    {
        var referencias = Dominio.GetReferencedAssemblies()
            .Select(r => r.Name ?? string.Empty)
            .ToList();

        var indevidas = referencias
            .Where(nome => Proibidos.Any(p => nome.StartsWith(p, StringComparison.Ordinal)))
            .ToList();

        Assert.True(
            indevidas.Count == 0,
            $"O Domain passou a depender de: {string.Join(", ", indevidas)}");
    }

    [Fact]
    public void Dominio_NaoUsaNenhumPacoteDeTerceiros()
    {
        // A lista de referencias do Domain deve ser so a biblioteca padrao.
        var deTerceiros = Dominio.GetReferencedAssemblies()
            .Select(r => r.Name ?? string.Empty)
            .Where(nome =>
                !nome.StartsWith("System", StringComparison.Ordinal) &&
                !nome.Equals("netstandard", StringComparison.Ordinal) &&
                !nome.Equals("mscorlib", StringComparison.Ordinal))
            .ToList();

        Assert.True(
            deTerceiros.Count == 0,
            $"Pacote de terceiro no Domain: {string.Join(", ", deTerceiros)}");
    }

    [Fact]
    public void EntidadesNaoExpoemSetterPublico()
    {
        // Setter publico permitiria contornar a validacao: bastaria atribuir
        // Nome direto para gravar um cliente sem nome no banco.
        var tipos = new[] { typeof(Cliente), typeof(RegistroHistorico) };

        var abertas = tipos
            .SelectMany(tipo => tipo.GetProperties(BindingFlags.Public | BindingFlags.Instance))
            .Where(propriedade => propriedade.SetMethod?.IsPublic == true)
            .Select(propriedade => $"{propriedade.DeclaringType!.Name}.{propriedade.Name}")
            .ToList();

        Assert.True(abertas.Count == 0, $"Propriedade com setter publico: {string.Join(", ", abertas)}");
    }
}
