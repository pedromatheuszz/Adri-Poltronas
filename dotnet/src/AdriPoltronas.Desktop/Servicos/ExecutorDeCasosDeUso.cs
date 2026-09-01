using Microsoft.Extensions.DependencyInjection;

namespace AdriPoltronas.Desktop.Servicos;

/// <summary>
/// Resolve um caso de uso dentro do proprio escopo e o executa.
/// </summary>
/// <remarks>
/// Existe por causa do tempo de vida do <c>DbContext</c>. Os ViewModels vivem
/// enquanto a janela estiver aberta; o contexto do Entity Framework nao pode
/// viver tanto -- ele acumularia entidades rastreadas de todas as edicoes da
/// sessao e, mais cedo ou mais tarde, gravaria alteracao que o operador ja
/// tinha descartado.
///
/// Cada chamada abre um escopo, usa um contexto novo e o descarta. Sem isto,
/// os ViewModels precisariam repetir cinco linhas de <c>CreateAsyncScope</c>
/// em cada comando.
/// </remarks>
public sealed class ExecutorDeCasosDeUso(IServiceScopeFactory fabrica)
{
    public async Task<TResultado> ExecutarAsync<TCasoDeUso, TResultado>(
        Func<TCasoDeUso, Task<TResultado>> operacao)
        where TCasoDeUso : notnull
    {
        await using var escopo = fabrica.CreateAsyncScope();
        var casoDeUso = escopo.ServiceProvider.GetRequiredService<TCasoDeUso>();
        return await operacao(casoDeUso);
    }
}
