namespace AdriPoltronas.Domain.Exceptions;

/// <summary>Falha causada por uma regra do negocio, nao por um defeito tecnico.</summary>
public class DomainException : Exception
{
    public DomainException(string mensagem) : base(mensagem)
    {
    }
}

/// <summary>
/// Dados que nao satisfazem as regras do cadastro.
/// </summary>
/// <remarks>
/// Carrega a lista inteira de problemas, e nao so o primeiro: o formulario
/// mostra tudo de uma vez em vez de fazer o operador descobrir os erros um a
/// um, que era o comportamento do backend Python que esta camada substitui.
/// </remarks>
public sealed class ValidacaoException : DomainException
{
    public ValidacaoException(IReadOnlyList<string> erros)
        : base(string.Join(" ", erros))
    {
        Erros = erros;
    }

    public IReadOnlyList<string> Erros { get; }
}
