namespace AdriPoltronas.Desktop.Servicos;

/// <summary>
/// Executa algo no thread da interface.
/// </summary>
/// <remarks>
/// Existe para tirar o <c>Dispatcher.UIThread</c> estatico de dentro dos
/// ViewModels. Com a chamada estatica, testar um ViewModel exigia inicializar
/// o Avalonia inteiro -- ou o teste travava esperando um dispatcher que nunca
/// roda. Com a interface, o teste passa um dublê sincrono.
/// </remarks>
public interface IDespachante
{
    Task NaInterfaceAsync(Action acao);
}
