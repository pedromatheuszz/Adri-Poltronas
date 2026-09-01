using System.Text.RegularExpressions;

namespace AdriPoltronas.Domain.Rules;

/// <summary>
/// Normalizacao e limites dos campos de texto do cadastro.
/// </summary>
/// <remarks>
/// As regras vieram de <c>backend/validators.py</c>, que era o unico lugar em
/// que existiam. Ficam aqui, e nao no formulario, porque valem para qualquer
/// origem do dado -- tela, importacao de planilha ou script.
/// </remarks>
public static partial class TextoDoCadastro
{
    public const int NomeMinimo = 2;
    public const int NomeMaximo = 120;
    public const int EnderecoMaximo = 160;
    public const int CidadeMaxima = 80;
    public const int ObservacoesMaximas = 1000;

    /// <summary>
    /// Letras (com acento), digitos, espacos e a pontuacao que aparece em
    /// nomes e enderecos brasileiros. Bloqueia o resto -- sinais que so
    /// aparecem em tentativa de injecao nao tem uso num cadastro.
    /// </summary>
    [GeneratedRegex(@"^[\w\sÀ-ÿ'.,\-()/]+$")]
    private static partial Regex CaracteresAceitos();

    /// <summary>Tira espaco das pontas, colapsa espacos internos e corta no limite.</summary>
    public static string Normalizar(string? valor, int tamanhoMaximo)
    {
        if (string.IsNullOrWhiteSpace(valor))
        {
            return string.Empty;
        }

        var semExcesso = EspacosSeguidos().Replace(valor.Trim(), " ");
        return semExcesso.Length <= tamanhoMaximo
            ? semExcesso
            : semExcesso[..tamanhoMaximo];
    }

    [GeneratedRegex(@"\s+")]
    private static partial Regex EspacosSeguidos();

    /// <summary>
    /// Valida um campo ja normalizado e acumula a mensagem em <paramref name="erros"/>.
    /// </summary>
    public static void Exigir(
        string valor,
        string rotulo,
        int tamanhoMaximo,
        List<string> erros,
        int tamanhoMinimo = 1)
    {
        if (valor.Length < tamanhoMinimo)
        {
            erros.Add(tamanhoMinimo > 1
                ? $"{rotulo} obrigatorio (entre {tamanhoMinimo} e {tamanhoMaximo} caracteres)."
                : $"{rotulo} obrigatorio (ate {tamanhoMaximo} caracteres).");
            return;
        }

        if (valor.Length > tamanhoMaximo)
        {
            erros.Add($"{rotulo} deve ter ate {tamanhoMaximo} caracteres.");
            return;
        }

        if (!CaracteresAceitos().IsMatch(valor))
        {
            erros.Add($"{rotulo} contem caracteres invalidos.");
        }
    }
}
