using System.Collections.Concurrent;
using AdriPoltronas.Infrastructure.Sistema;
using Microsoft.Extensions.Logging;

namespace AdriPoltronas.Desktop.Logging;

/// <summary>
/// Provedor de log que escreve em arquivo diario.
/// </summary>
/// <remarks>
/// Um aplicativo de desktop empacotado nao tem console: sem arquivo, o log do
/// unico ambiente que importa -- a maquina de quem usa o sistema -- se perde.
/// O provedor de console continua registrado para o desenvolvimento.
///
/// Sao poucas linhas escritas a mao, e nao um Serilog: a necessidade e "grave
/// linha de texto em arquivo", e uma dependencia a mais para isso nao se
/// justifica.
/// </remarks>
public sealed class ProvedorDeLogEmArquivo(LogLevel minimo) : ILoggerProvider
{
    private readonly ConcurrentDictionary<string, LogEmArquivo> _registradores = new();
    private readonly object _trava = new();

    public ILogger CreateLogger(string categoria) =>
        _registradores.GetOrAdd(categoria, nome => new LogEmArquivo(nome, minimo, Escrever));

    private void Escrever(string linha)
    {
        try
        {
            var arquivo = Path.Combine(
                PastaDeDados.PastaDeLogs(), $"desktop-{DateTime.Now:yyyy-MM-dd}.log");

            // Um lock simples: o volume e de dezenas de linhas por sessao, e
            // perder uma mensagem por corrida seria pior do que a espera.
            lock (_trava)
            {
                File.AppendAllText(arquivo, linha + Environment.NewLine);
            }
        }
        catch (Exception)
        {
            // Log que derruba o aplicativo e pior do que log ausente: disco
            // cheio ou pasta sem permissao nao podem impedir o uso do sistema.
        }
    }

    public void Dispose() => _registradores.Clear();
}

internal sealed class LogEmArquivo(string categoria, LogLevel minimo, Action<string> escrever)
    : ILogger
{
    public IDisposable? BeginScope<TState>(TState estado) where TState : notnull => null;

    public bool IsEnabled(LogLevel nivel) => nivel >= minimo && nivel != LogLevel.None;

    public void Log<TState>(
        LogLevel nivel,
        EventId evento,
        TState estado,
        Exception? excecao,
        Func<TState, Exception?, string> formatar)
    {
        if (!IsEnabled(nivel))
        {
            return;
        }

        var texto = $"{DateTime.Now:yyyy-MM-dd HH:mm:ss} [{nivel}] {categoria}: " +
                    formatar(estado, excecao);
        if (excecao is not null)
        {
            texto += Environment.NewLine + excecao;
        }

        escrever(texto);
    }
}
