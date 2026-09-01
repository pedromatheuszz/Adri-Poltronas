using AdriPoltronas.Desktop.ViewModels;

namespace AdriPoltronas.Desktop.Navigation;

/// <summary>
/// Troca a tela exibida.
/// </summary>
/// <remarks>
/// Trabalha com ViewModels, nunca com Views: um ViewModel que instanciasse
/// <c>new ClientesView()</c> passaria a depender do controle concreto e
/// deixaria de ser testavel sem uma janela aberta. Quem escolhe a View
/// correspondente e o <c>ViewLocator</c>, por convencao de nome.
/// </remarks>
public interface INavegacao
{
    ViewModelBase? Atual { get; }

    event Action<ViewModelBase>? Mudou;

    void IrPara<TViewModel>() where TViewModel : ViewModelBase;
}
