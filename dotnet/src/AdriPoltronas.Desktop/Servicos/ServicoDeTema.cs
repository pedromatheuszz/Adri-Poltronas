using AdriPoltronas.Infrastructure.Sistema;
using Avalonia.Styling;
using Microsoft.Extensions.Logging;

namespace AdriPoltronas.Desktop.Servicos;

/// <summary>
/// Troca o tema e lembra a escolha entre execucoes.
/// </summary>
/// <remarks>
/// A escolha vai para um arquivo na pasta do usuario, e nao para o banco: e
/// preferencia de quem esta na maquina, nao dado do negocio, e uma coluna nova
/// divergiria do schema que o backend Python compartilha.
/// </remarks>
public sealed class ServicoDeTema(ILogger<ServicoDeTema> log) : ITema
{
    private const string NomeDoArquivo = "tema.txt";
    private const string Escuro = "escuro";
    private const string Claro = "claro";

    public bool EstaEscuro { get; private set; } = true;

    public void Restaurar()
    {
        EstaEscuro = Ler() != Claro;
        Aplicar();
    }

    public void Alternar()
    {
        EstaEscuro = !EstaEscuro;
        Aplicar();
        Gravar(EstaEscuro ? Escuro : Claro);
    }

    private void Aplicar()
    {
        var aplicacao = Avalonia.Application.Current;
        if (aplicacao is not null)
        {
            aplicacao.RequestedThemeVariant = EstaEscuro ? ThemeVariant.Dark : ThemeVariant.Light;
        }
    }

    private string Ler()
    {
        try
        {
            var caminho = Caminho();
            return File.Exists(caminho) ? File.ReadAllText(caminho).Trim() : Escuro;
        }
        catch (IOException erro)
        {
            // Preferencia ilegivel nao impede o app de abrir: volta ao escuro.
            log.LogWarning(erro, "Preferencia de tema ilegivel; usando o tema escuro.");
            return Escuro;
        }
    }

    private void Gravar(string valor)
    {
        try
        {
            File.WriteAllText(Caminho(), valor);
        }
        catch (IOException erro)
        {
            log.LogWarning(erro, "Nao foi possivel guardar a preferencia de tema.");
        }
    }

    private static string Caminho() => Path.Combine(PastaDeDados.Raiz(), NomeDoArquivo);
}
