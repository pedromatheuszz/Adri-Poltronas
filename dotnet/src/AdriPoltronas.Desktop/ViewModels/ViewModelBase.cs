using CommunityToolkit.Mvvm.ComponentModel;

namespace AdriPoltronas.Desktop.ViewModels;

/// <summary>
/// Base dos ViewModels: notificacao de mudanca, estado de ocupado e mensagem.
/// </summary>
/// <remarks>
/// <see cref="ObservableObject"/> vem do CommunityToolkit e gera o
/// <c>INotifyPropertyChanged</c> em tempo de compilacao. E o unico pacote de
/// MVVM do projeto: nao ha framework de mensageria nem service locator, porque
/// navegacao e dialogo ja sao servicos injetados.
/// </remarks>
public abstract partial class ViewModelBase : ObservableObject
{
    [ObservableProperty]
    private bool _ocupado;

    /// <summary>Ultima mensagem para a barra de status.</summary>
    [ObservableProperty]
    private string _mensagem = string.Empty;

    /// <summary>Chamado pela navegacao quando a tela passa a ser exibida.</summary>
    public virtual void AoEntrar()
    {
    }

    /// <summary>
    /// Roda uma operacao marcando <see cref="Ocupado"/> e capturando o que
    /// escapou.
    /// </summary>
    /// <remarks>
    /// Concentra aqui o try/catch que, sem isso, se repetiria em cada comando.
    /// Falha esperada (dado invalido, registro inexistente) nao chega a este
    /// ponto: vem como <c>Resultado</c> do caso de uso. O que sobra e mesmo
    /// imprevisto, e ai o certo e avisar o operador em vez de derrubar a
    /// janela.
    /// </remarks>
    protected async Task ExecutarAsync(Func<Task> operacao, string mensagemDeErro)
    {
        if (Ocupado)
        {
            return;
        }

        Ocupado = true;
        try
        {
            await operacao();
        }
        catch (Exception erro)
        {
            RegistrarFalha(erro, mensagemDeErro);
            Mensagem = mensagemDeErro;
        }
        finally
        {
            Ocupado = false;
        }
    }

    /// <summary>Onde a classe concreta manda o erro para o log.</summary>
    protected abstract void RegistrarFalha(Exception erro, string contexto);
}
