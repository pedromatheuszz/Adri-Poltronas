namespace AdriPoltronas.Application.Common;

/// <summary>Por que um caso de uso nao concluiu.</summary>
public enum TipoDeFalha
{
    Nenhuma = 0,
    Validacao = 1,
    NaoEncontrado = 2,
    Conflito = 3,
    Infraestrutura = 4,
}

/// <summary>
/// Desfecho de um caso de uso, sem excecao.
/// </summary>
/// <remarks>
/// Dado invalido e cliente inexistente sao resultados esperados de um
/// formulario, nao acidentes: modelar como excecao obrigaria um try/catch em
/// volta de cada chamada no ViewModel -- exatamente o ruido que o pedido de
/// padronizacao de erros manda evitar. Excecao fica para o que e mesmo
/// imprevisto, e ai o handler global cuida.
/// </remarks>
public class Resultado
{
    protected Resultado(TipoDeFalha falha, IReadOnlyList<string> erros)
    {
        Falha = falha;
        Erros = erros;
    }

    public TipoDeFalha Falha { get; }
    public IReadOnlyList<string> Erros { get; }
    public bool Sucesso => Falha == TipoDeFalha.Nenhuma;

    /// <summary>Mensagem unica, pronta para a barra de status.</summary>
    public string Mensagem => string.Join(" ", Erros);

    public static Resultado Ok() => new(TipoDeFalha.Nenhuma, []);

    public static Resultado Invalido(IReadOnlyList<string> erros) =>
        new(TipoDeFalha.Validacao, erros);

    public static Resultado NaoEncontrado(string mensagem) =>
        new(TipoDeFalha.NaoEncontrado, [mensagem]);

    public static Resultado Conflito(string mensagem) =>
        new(TipoDeFalha.Conflito, [mensagem]);
}

/// <summary>Resultado que devolve um valor quando da certo.</summary>
public sealed class Resultado<T> : Resultado
{
    private Resultado(T? valor, TipoDeFalha falha, IReadOnlyList<string> erros)
        : base(falha, erros) => Valor = valor;

    public T? Valor { get; }

    public static Resultado<T> Ok(T valor) => new(valor, TipoDeFalha.Nenhuma, []);

    public static new Resultado<T> Invalido(IReadOnlyList<string> erros) =>
        new(default, TipoDeFalha.Validacao, erros);

    public static new Resultado<T> NaoEncontrado(string mensagem) =>
        new(default, TipoDeFalha.NaoEncontrado, [mensagem]);
}
