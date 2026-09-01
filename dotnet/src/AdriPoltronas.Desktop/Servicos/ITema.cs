namespace AdriPoltronas.Desktop.Servicos;

/// <summary>
/// Tema visual da aplicacao, claro ou escuro.
/// </summary>
/// <remarks>
/// Abstraido para que o ViewModel do cabecalho nao toque em
/// <c>Application.Current</c>: com a chamada estatica, testar o botao de tema
/// exigiria subir o Avalonia inteiro.
/// </remarks>
public interface ITema
{
    bool EstaEscuro { get; }

    void Alternar();

    /// <summary>Aplica o tema guardado da ultima sessao.</summary>
    void Restaurar();
}
