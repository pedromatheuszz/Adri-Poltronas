using CommunityToolkit.Mvvm.Input;

namespace AdriPoltronas.Desktop.ViewModels;

/// <summary>
/// Tela que responde aos atalhos globais do teclado.
/// </summary>
/// <remarks>
/// A janela principal e quem escuta as teclas, porque o atalho precisa
/// funcionar com o foco em qualquer lugar. Ela nao pode conhecer cada tela,
/// entao pergunta por esta interface -- tela que nao a implementa simplesmente
/// ignora o atalho, sem <c>if</c> por tipo espalhado.
/// </remarks>
public interface IAtalhosDeTela
{
    /// <summary>Ctrl+N. Nulo quando a tela nao cadastra nada.</summary>
    IRelayCommand? ComandoNovo { get; }

    /// <summary>Ctrl+R.</summary>
    IRelayCommand? ComandoAtualizar { get; }
}
