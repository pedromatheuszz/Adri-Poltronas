using AdriPoltronas.Desktop.ViewModels;
using Microsoft.Extensions.DependencyInjection;

namespace AdriPoltronas.Desktop.Navigation;

/// <inheritdoc cref="INavegacao"/>
public sealed class Navegacao(IServiceProvider servicos) : INavegacao
{
    public ViewModelBase? Atual { get; private set; }

    public event Action<ViewModelBase>? Mudou;

    public void IrPara<TViewModel>() where TViewModel : ViewModelBase
    {
        // O ViewModel vem do container: ele recebe as dependencias por
        // construtor como qualquer outro servico, sem `new` espalhado.
        var destino = servicos.GetRequiredService<TViewModel>();
        Atual = destino;
        Mudou?.Invoke(destino);
        destino.AoEntrar();
    }
}
